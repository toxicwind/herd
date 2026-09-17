#!/usr/bin/env python3
"""
Sovereign AST Matrix v3 — Maximal free coding gateway for Zed
=============================================================
Merged from:
  - MrFadiAi/free-llm-gateway (Python OpenAI compat + fallback + rate tracking)
  - tashfeenahmed/freellmapi (TS routing strategies, sticky sessions, context handoff)
  - vava-nessa/free-coding-models (coding model focus, daemon endpoint, catalog)

5 routing strategies (research-backed: RouteLLM, agent-router, PORT,
LLM-Runner-Router, radlab llm-router, circuit-breaker patterns):
  1. fifo_matrix      — bounded FIFO queue, back-pressure
  2. ast_race         — parallel race of 4; first AST/code-shaped response wins
  3. sticky_affinity  — session sticky 30 min for multi-turn coherence
  4. weighted_elo     — dynamic weight from recent success/latency (RouteLLM-style)
  5. circuit_chain    — sequential fallback with circuit-breaker open/half-open

Default: hybrid (sticky → ast_race of top-weighted → circuit_chain on failure).

CRITICAL: Full SSE streaming proxy — Zed sends stream:true, we stream chunks back.
No local GPU provider. Cloud-only (NVIDIA NIM + OpenRouter free tier).

Run: python3 router.py
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import random
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutTimeout
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Load secrets from ~/.secrets (key=value pairs, with or without export)
# ---------------------------------------------------------------------------
def _load_secrets():
    for path in (os.path.expanduser("~/.secrets"), "/home/toxic/.secrets"):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Strip 'export ' prefix
                    if line.startswith("export "):
                        line = line[7:]
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and v:
                            os.environ.setdefault(k, v)
        except FileNotFoundError:
            pass

_load_secrets()

PORT = int(os.getenv("SOVEREIGN_PORT", "19281"))
DB = os.getenv("SOVEREIGN_DB", "/tmp/sovereign_ast_matrix.db")
MAX_PARALLEL = 4
STICKY_TTL = 1800
FIFO_MAX = 64
STRATEGY = os.getenv("SOVEREIGN_STRATEGY", "hybrid")

# ---------------------------------------------------------------------------
# Provider model mappings — every provider has explicit model IDs
# ---------------------------------------------------------------------------
PROVIDER_MODELS: Dict[str, List[str]] = {
    "openrouter": [
        # Free coding models (OpenRouter :free suffix)
        "tencent/hy3:free",
        "poolside/laguna-m.1:free",
        "poolside/laguna-xs-2.1:free",
        "qwen/qwen3-coder:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "cohere/north-mini-code:free",
        "openai/gpt-oss-20b:free",
    ],
    "nvidia": [
        # NVIDIA NIM direct (build.nvidia.com)
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-30b-a3b",
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-405b-instruct",
        "meta/llama-3.1-70b-instruct",
        "qwen/qwen3-coder-480b-a35b-instruct",
        "qwen/qwen2.5-coder-32b-instruct",
        "deepseek-ai/deepseek-r1",
        "deepseek-ai/deepseek-v3",
        "mistralai/mistral-large-2-instruct",
        "microsoft/phi-4",
        "google/gemma-3-27b-it",
        "zai-org/glm-4.5",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "cerebras": [
        "llama3.1-70b",
        "qwen-3-235b",
    ],
    "google": [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    "mistral": [
        "mistral-large-latest",
        "codestral-latest",
        "mistral-small-latest",
    ],
}

# Friendly alias → (provider, actual_model_id)
CODING: Dict[str, Optional[Tuple[str, str]]] = {
    "auto": None,
    "fcm": None,
    # OpenRouter free
    "hy3": ("openrouter", "tencent/hy3:free"),
    "laguna-m1": ("openrouter", "poolside/laguna-m.1:free"),
    "laguna-xs": ("openrouter", "poolside/laguna-xs-2.1:free"),
    "qwen3-coder": ("openrouter", "qwen/qwen3-coder:free"),
    "gemma4-31b": ("openrouter", "google/gemma-4-31b-it:free"),
    "gemma4-26b": ("openrouter", "google/gemma-4-26b-a4b-it:free"),
    "nemotron-super": ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    "nemotron-nano": ("openrouter", "nvidia/nemotron-3-nano-30b-a3b:free"),
    "north-mini": ("openrouter", "cohere/north-mini-code:free"),
    "gpt-oss": ("openrouter", "openai/gpt-oss-20b:free"),
    # NVIDIA NIM direct
    "nim-nemotron-super": ("nvidia", "nvidia/nemotron-3-super-120b-a12b"),
    "nim-nemotron-nano": ("nvidia", "nvidia/nemotron-3-nano-30b-a3b"),
    "nim-llama-3.3-70b": ("nvidia", "meta/llama-3.3-70b-instruct"),
    "nim-llama-3.1-405b": ("nvidia", "meta/llama-3.1-405b-instruct"),
    "nim-llama-3.1-70b": ("nvidia", "meta/llama-3.1-70b-instruct"),
    "nim-qwen3-coder": ("nvidia", "qwen/qwen3-coder-480b-a35b-instruct"),
    "nim-qwen2.5-coder-32b": ("nvidia", "qwen/qwen2.5-coder-32b-instruct"),
    "nim-deepseek-r1": ("nvidia", "deepseek-ai/deepseek-r1"),
    "nim-deepseek-v3": ("nvidia", "deepseek-ai/deepseek-v3"),
    "nim-mistral-large": ("nvidia", "mistralai/mistral-large-2-instruct"),
    "nim-phi-4": ("nvidia", "microsoft/phi-4"),
    "nim-gemma-3-27b": ("nvidia", "google/gemma-3-27b-it"),
    "nim-glm": ("nvidia", "zai-org/glm-4.5"),
}

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "openrouter": {
        "base": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
    },
    "nvidia": {
        "base": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "key_env_alt": "NVIDIA_NIM_API_KEY",
    },
    "groq": {
        "base": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
    },
    "cerebras": {
        "base": "https://api.cerebras.ai/v1",
        "key_env": "CEREBRAS_API_KEY",
    },
    "google": {
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GOOGLE_API_KEY",
    },
    "mistral": {
        "base": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
    },
}

# AST/code detection for race strategy
AST_RE = re.compile(
    r"(def |class |import |from |function |const |let |var |#include|package |fn |pub |struct |impl |"
    r"async |await |\.ts|\.py|\.rs|\.js|AST|tree-sitter|syntax|```)",
    re.I,
)


# ---------------------------------------------------------------------------
# State: ELO, circuit breakers, sticky, FIFO, SQLite audit
# ---------------------------------------------------------------------------
class Matrix:
    def __init__(self):
        self.lock = threading.Lock()
        self.sticky: Dict[str, Tuple[str, str, float]] = {}
        self.fail: Dict[str, Tuple[int, float]] = {}
        self.elo: Dict[str, float] = {p: 1000.0 for p in PROVIDERS}
        self.circuit: Dict[str, str] = {p: "closed" for p in PROVIDERS}
        self.circuit_open_until: Dict[str, float] = {}
        self.fifo = queue.Queue(maxsize=FIFO_MAX)
        self.conn = sqlite3.connect(DB, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS reqs "
            "(ts REAL, model TEXT, provider TEXT, status INT, lat REAL, winner INT, strategy TEXT)"
        )
        self.conn.commit()

    def record(
        self,
        model: str,
        prov: str,
        status: int,
        lat: float,
        winner: int = 0,
        strategy: str = "",
    ):
        with self.lock:
            self.conn.execute(
                "INSERT INTO reqs VALUES (?,?,?,?,?,?,?)",
                (time.time(), model, prov, status, lat, winner, strategy),
            )
            self.conn.commit()
            if status == 200:
                self.elo[prov] = self.elo.get(prov, 1000) + 16
                self.fail[prov] = (0, time.time())
                self.circuit[prov] = "closed"
            else:
                c, _ = self.fail.get(prov, (0, 0))
                self.fail[prov] = (c + 1, time.time())
                self.elo[prov] = max(100.0, self.elo.get(prov, 1000) - 32)
                if c + 1 >= 3:
                    self.circuit[prov] = "open"
                    self.circuit_open_until[prov] = time.time() + 60

    def sticky_get(self, sid: str) -> Tuple[Optional[str], Optional[str]]:
        with self.lock:
            if sid in self.sticky:
                p, m, t = self.sticky[sid]
                if time.time() - t < STICKY_TTL:
                    return p, m
                del self.sticky[sid]
        return None, None

    def sticky_set(self, sid: str, p: str, m: str):
        with self.lock:
            self.sticky[sid] = (p, m, time.time())

    def circuit_ok(self, p: str) -> bool:
        st = self.circuit.get(p, "closed")
        if st == "closed":
            return True
        if st == "open":
            if time.time() > self.circuit_open_until.get(p, 0):
                self.circuit[p] = "half"
                return True
            return False
        return True  # half-open: allow probe


state = Matrix()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_key(p: str) -> str:
    """Resolve API key from env, trying primary and alt env vars."""
    conf = PROVIDERS[p]
    env = conf.get("key_env", "")
    alt = conf.get("key_env_alt", "")
    k = os.getenv(env, "") or (os.getenv(alt, "") if alt else "") or ""
    return k


def key_ok(p: str) -> bool:
    return bool(get_key(p))


def first_model_for(p: str) -> str:
    """Return the first available model ID for a provider."""
    models = PROVIDER_MODELS.get(p, [])
    return models[0] if models else ""


def resolve_model(model: str) -> Tuple[str, str]:
    """Resolve a model request to (provider, actual_model_id).

    Handles: named aliases (hy3, nim-llama-3.3-70b), auto/fcm, and raw model IDs.
    """
    # Named alias
    if model in CODING and CODING[model]:
        return CODING[model]
    # auto/fcm → first available provider
    if model in ("auto", "fcm"):
        # Prefer openrouter (free tier), then nvidia (we have key), then others
        for p in ("openrouter", "nvidia", "groq", "cerebras", "google", "mistral"):
            if key_ok(p):
                mid = first_model_for(p)
                if mid:
                    return p, mid
        return "openrouter", "tencent/hy3:free"
    # Raw model ID — figure out which provider it belongs to
    for p, models in PROVIDER_MODELS.items():
        if model in models:
            return p, model
    # Unknown model — best effort: try openrouter free, then nvidia
    if key_ok("openrouter"):
        return "openrouter", model
    if key_ok("nvidia"):
        return "nvidia", model
    return "openrouter", "tencent/hy3:free"


def is_ast(text: str) -> bool:
    return bool(text and (AST_RE.search(text[:5000]) or "```" in text))


# ---------------------------------------------------------------------------
# Provider call — supports streaming
# ---------------------------------------------------------------------------
def call_one(provider: str, model: str, body: dict) -> dict:
    """Call a single provider. Returns full response or streaming chunks."""
    if not state.circuit_ok(provider):
        return {
            "ok": False,
            "status": 503,
            "provider": provider,
            "lat": 0,
            "err": "circuit_open",
        }
    conf = PROVIDERS[provider]
    url = conf["base"].rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_key(provider)}",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://zed.dev"
        headers["X-Title"] = "Sovereign-AST-Matrix"
    data = json.dumps({**body, "model": model}).encode()
    start = time.time()
    try:
        req = Request(url, data=data, headers=headers, method="POST")
        resp = urlopen(req, timeout=120)
        lat = time.time() - start
        is_stream = body.get("stream", False)
        if is_stream:
            return {
                "ok": True,
                "status": resp.status,
                "resp": resp,
                "provider": provider,
                "model": model,
                "lat": lat,
                "stream": True,
            }
        raw = resp.read()
        state.record(model, provider, resp.status, lat, strategy=STRATEGY)
        if state.circuit.get(provider) == "half":
            state.circuit[provider] = "closed"
        return {
            "ok": True,
            "status": resp.status,
            "data": raw,
            "provider": provider,
            "model": model,
            "lat": lat,
        }
    except HTTPError as e:
        lat = time.time() - start
        state.record(model, provider, e.code, lat, strategy=STRATEGY)
        return {
            "ok": False,
            "status": e.code,
            "provider": provider,
            "lat": lat,
            "err": str(e.read()[:500]),
        }
    except Exception as e:
        lat = time.time() - start
        state.record(model, provider, 500, lat, strategy=STRATEGY)
        return {
            "ok": False,
            "status": 500,
            "provider": provider,
            "lat": lat,
            "err": str(e),
        }


def call_one_stream(provider: str, model: str, body: dict) -> dict:
    """Call provider with streaming. Returns raw response object for SSE proxy."""
    if not state.circuit_ok(provider):
        return {
            "ok": False,
            "status": 503,
            "provider": provider,
            "lat": 0,
            "err": "circuit_open",
        }
    conf = PROVIDERS[provider]
    url = conf["base"].rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_key(provider)}",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://zed.dev"
        headers["X-Title"] = "Sovereign-AST-Matrix"
    stream_body = {**body, "model": model, "stream": True}
    data = json.dumps(stream_body).encode()
    start = time.time()
    try:
        req = Request(url, data=data, headers=headers, method="POST")
        resp = urlopen(req, timeout=180)
        lat = time.time() - start
        state.record(model, provider, 200, lat, strategy=STRATEGY)
        if state.circuit.get(provider) == "half":
            state.circuit[provider] = "closed"
        return {
            "ok": True,
            "status": resp.status,
            "resp": resp,
            "provider": provider,
            "model": model,
            "lat": lat,
            "stream": True,
        }
    except HTTPError as e:
        lat = time.time() - start
        state.record(model, provider, e.code, lat, strategy=STRATEGY)
        return {
            "ok": False,
            "status": e.code,
            "provider": provider,
            "lat": lat,
            "err": str(e.read()[:500]),
        }
    except Exception as e:
        lat = time.time() - start
        state.record(model, provider, 500, lat, strategy=STRATEGY)
        return {
            "ok": False,
            "status": 500,
            "provider": provider,
            "lat": lat,
            "err": str(e),
        }


# ---------------------------------------------------------------------------
# Strategy: pick weighted candidates (ELO + jitter, no dead providers)
# ---------------------------------------------------------------------------
def pick_weighted(n: int = MAX_PARALLEL) -> List[Tuple[str, str]]:
    scored = []
    for p in PROVIDERS:
        if not key_ok(p) or not state.circuit_ok(p):
            continue
        sc = state.elo.get(p, 1000) + random.random() * 10
        mid = first_model_for(p)
        if mid:
            scored.append((sc, p, mid))
    scored.sort(reverse=True)
    out, seen = [], set()
    for _, p, mid in scored:
        if p not in seen:
            seen.add(p)
            out.append((p, mid))
        if len(out) >= n:
            break
    # Fallback: openrouter free if nothing else available
    if not out and key_ok("openrouter"):
        out = [("openrouter", "tencent/hy3:free")]
    return out


# ---------------------------------------------------------------------------
# Strategy routes
# ---------------------------------------------------------------------------
def route_ast_race(body: dict, session: str) -> dict:
    model = body.get("model", "auto")
    if model in CODING and CODING[model]:
        cands = [CODING[model]]
    else:
        cands = pick_weighted(MAX_PARALLEL)
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
        futs = {ex.submit(call_one, p, mid, body): (p, mid) for p, mid in cands}
        best = None
        try:
            for fut in as_completed(futs, timeout=95):
                r = fut.result()
                if not r.get("ok"):
                    continue
                try:
                    j = json.loads(r["data"])
                    content = (
                        j.get("choices", [{}])[0].get("message", {}).get("content", "")
                    )
                except Exception:
                    content = ""
                if is_ast(content):
                    state.sticky_set(session, r["provider"], r["model"])
                    state.record(
                        r["model"],
                        r["provider"],
                        200,
                        r["lat"],
                        winner=1,
                        strategy="ast_race",
                    )
                    return r
                if best is None:
                    best = r
        except FutTimeout:
            pass
        if best:
            state.sticky_set(session, best["provider"], best["model"])
            return best
    return {"ok": False, "status": 503, "err": "ast_race_exhausted"}


def route_sticky(body: dict, session: str) -> dict:
    p, m = state.sticky_get(session)
    if p and key_ok(p) and state.circuit_ok(p):
        r = call_one(p, m or body.get("model", "auto"), body)
        if r.get("ok"):
            return r
    return route_ast_race(body, session)


def route_weighted(body: dict, session: str) -> dict:
    cands = pick_weighted(1)
    if not cands:
        return {"ok": False, "status": 503, "err": "no_providers"}
    p, mid = cands[0]
    r = call_one(p, mid, body)
    if r.get("ok"):
        state.sticky_set(session, p, mid)
    return r


def route_circuit_chain(body: dict, session: str) -> dict:
    order = sorted(PROVIDERS.keys(), key=lambda p: -state.elo.get(p, 1000))
    for p in order:
        if not key_ok(p) or not state.circuit_ok(p):
            continue
        mid = first_model_for(p)
        if not mid:
            continue
        r = call_one(p, mid, body)
        if r.get("ok"):
            state.sticky_set(session, p, mid)
            return r
    return {"ok": False, "status": 503, "err": "circuit_chain_exhausted"}


def route_fifo(body: dict, session: str) -> dict:
    try:
        state.fifo.put_nowait(1)
    except queue.Full:
        return {"ok": False, "status": 429, "err": "fifo_full"}
    try:
        return route_ast_race(body, session)
    finally:
        try:
            state.fifo.get_nowait()
        except Exception:
            pass


def route_hybrid(body: dict, session: str) -> dict:
    p, m = state.sticky_get(session)
    if p and key_ok(p) and state.circuit_ok(p):
        r = call_one(p, m or body.get("model", "auto"), body)
        if r.get("ok"):
            return r
    r = route_ast_race(body, session)
    if r.get("ok"):
        return r
    return route_circuit_chain(body, session)


ROUTERS = {
    "fifo_matrix": route_fifo,
    "ast_race": route_ast_race,
    "sticky_affinity": route_sticky,
    "weighted_elo": route_weighted,
    "circuit_chain": route_circuit_chain,
    "hybrid": route_hybrid,
}


# ---------------------------------------------------------------------------
# Streaming SSE proxy — read chunks from upstream, write to client
# ---------------------------------------------------------------------------
def proxy_stream(resp, handler, provider: str, model: str) -> None:
    """Proxy SSE stream from upstream response to Zed client."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Routed-Via", f"{provider}/{model}")
    handler.end_headers()
    try:
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass  # client disconnected
    finally:
        resp.close()


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            ms = [{"id": k, "object": "model"} for k in CODING]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"object": "list", "data": ms}).encode())
        elif self.path == "/health":
            key_status = {}
            for p in PROVIDERS:
                k = get_key(p)
                key_status[p] = "configured" if k else "no_key"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "status": "ok",
                        "router": "sovereign-ast-matrix",
                        "version": "v3",
                        "strategy": STRATEGY,
                        "parallel": MAX_PARALLEL,
                        "providers": {
                            p: {
                                "keys": key_status[p],
                                "elo": round(state.elo.get(p, 1000), 1),
                                "circuit": state.circuit.get(p, "unknown"),
                                "models": len(PROVIDER_MODELS.get(p, [])),
                            }
                            for p in PROVIDERS
                        },
                    }
                ).encode()
            )
        elif self.path == "/debug/sqlite":
            try:
                rows = state.conn.execute(
                    "SELECT model, provider, status, count(*), avg(lat) FROM reqs "
                    "GROUP BY model, provider, status ORDER BY count(*) DESC LIMIT 20"
                ).fetchall()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if "/chat/completions" not in self.path:
            self.send_response(404)
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        sid = (
            self.headers.get("X-Session-Id")
            or hashlib.md5(
                json.dumps(body.get("messages", [])[:1]).encode()
            ).hexdigest()[:12]
        )
        strat = self.headers.get("X-Sovereign-Strategy", STRATEGY)
        is_stream = body.get("stream", False)

        if is_stream:
            self._handle_stream(body, sid, strat)
        else:
            self._handle_sync(body, sid, strat)

    def _handle_sync(self, body: dict, sid: str, strat: str):
        fn = ROUTERS.get(strat, route_hybrid)
        r = fn(body, sid)
        if r.get("ok"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Routed-Via", f"{r['provider']}/{r['model']}")
            self.send_header("X-Latency", str(round(r.get("lat", 0), 3)))
            self.send_header("X-Strategy", strat)
            self.end_headers()
            self.wfile.write(r["data"])
        else:
            self.send_response(r.get("status", 503))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "error": r.get("err", "exhausted"),
                        "status": r.get("status"),
                    }
                ).encode()
            )

    def _handle_stream(self, body: dict, sid: str, strat: str):
        """Stream SSE from the first available provider. Fallback on connection errors."""
        # Try sticky first
        sp, sm = state.sticky_get(sid)
        if sp and key_ok(sp) and state.circuit_ok(sp):
            r = call_one_stream(sp, sm or body.get("model", "auto"), body)
            if r.get("ok"):
                state.sticky_set(sid, sp, r["model"])
                proxy_stream(r["resp"], self, sp, r["model"])
                return

        # Try weighted candidates
        candidates = []
        model = body.get("model", "auto")
        if model in CODING and CODING[model]:
            candidates = [CODING[model]]
        else:
            candidates = pick_weighted(MAX_PARALLEL)

        for p, mid in candidates:
            r = call_one_stream(p, mid, body)
            if r.get("ok"):
                state.sticky_set(sid, p, mid)
                proxy_stream(r["resp"], self, p, mid)
                return

        # All failed — return error
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"error": "all_stream_providers_exhausted"}).encode()
        )


def main():
    print(f"Sovereign AST Matrix v3 on http://127.0.0.1:{PORT}/v1")
    print(
        f"Strategy={STRATEGY} | 5 routes: fifo_matrix, ast_race, sticky_affinity, weighted_elo, circuit_chain (+ hybrid)"
    )
    print(
        f"Streaming=SSE proxy | Providers: {', '.join(p for p in PROVIDERS if key_ok(p))}"
    )
    print(
        f"No local GPU. Cloud-only: NVIDIA NIM + OpenRouter + Groq + Cerebras + Google + Mistral"
    )
    print("Point Zed language_models.openai.api_url here.")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
