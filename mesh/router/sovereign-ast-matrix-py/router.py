#!/usr/bin/env python3
"""
Sovereign AST Matrix v3 — Maximal free coding gateway for Zed
=============================================================
5 routing strategies (research-backed: RouteLLM, agent-router, PORT,
LLM-Runner-Router, radlab llm-router, circuit-breaker patterns):
  1. fifo_matrix      — bounded FIFO queue, back-pressure
  2. ast_race         — parallel race of 4; first AST/code-shaped response wins
  3. sticky_affinity  — session sticky 30 min for multi-turn coherence
  4. weighted_elo     — dynamic weight from recent success/latency (RouteLLM-style)
  5. circuit_chain    — sequential fallback with circuit-breaker open/half-open

Default: hybrid (sticky -> ast_race of top-weighted -> circuit_chain on failure).

DB: SQLite WAL mode for model health tracking + healing detection.
    Tracks per-model-per-provider success rate, latency percentiles,
    rate-limit events, and healing recovery timestamps.

No local GPU. Cloud-only. Basedpyright-clean types.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import random
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutTimeout
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
ChatBody = dict[str, Any]
RouteResult = dict[str, Any]


# old TypedDict removed
# ok: bool
# status: int
# provider: str
# model: str
# lat: float
# data: bytes
# resp: Any
# stream: bool
# err: str
# winner: int


# ---------------------------------------------------------------------------
# Load secrets from ~/.secrets
# ---------------------------------------------------------------------------
def _load_secrets() -> None:
    for path in (os.path.expanduser("~/.secrets"), "/home/toxic/.secrets"):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
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

# Port SSOT: sovereign/.env.local AST_MATRIX_PORT=25104
# process-compose sets SOVEREIGN_PORT=${AST_MATRIX_PORT}; Zed hits :25104/v1
PORT = int(
    os.getenv("SOVEREIGN_PORT")
    or os.getenv("AST_MATRIX_PORT")
    or "25104"
)
DB = os.getenv("SOVEREIGN_DB", "/home/toxic/sovereign/data/ast_matrix.db")
MAX_PARALLEL = 4
STICKY_TTL = 1800
FIFO_MAX = 64
STRATEGY = os.getenv("SOVEREIGN_STRATEGY", "hybrid")

# ---------------------------------------------------------------------------
# Provider model mappings
# ---------------------------------------------------------------------------
PROVIDER_MODELS: dict[str, list[str]] = {
    "openrouter": [
        "tencent/hy3:free",
        "poolside/laguna-m.1:free",
        "poolside/laguna-xs-2.1:free",
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "qwen/qwen3-coder:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "openai/gpt-oss-20b:free",
    ],
    "nvidia": [
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-30b-a3b",
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.3-70b-instruct",
        "qwen/qwen3.5-397b-a17b",
        "qwen/qwen3.5-122b-a10b",
        "deepseek-ai/deepseek-v4-flash",
        "deepseek-ai/deepseek-v4-pro",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "google/gemma-4-31b-it",
        "z-ai/glm-5.2",
        "thinkingmachines/inkling",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "qwen/qwen3-32b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ],
    "cerebras": [
        # all 403 - key issue
    ],
    "google": [
        "models/gemini-2.5-flash",
        "models/gemini-2.5-flash-lite",
        "models/gemini-2.0-flash",
        "models/gemma-4-31b-it",
    ],
    "mistral": [
        "mistral-small-latest",
        "codestral-latest",
        "mistral-large-latest",
        "mistral-medium-latest",
    ],
}

# Friendly alias -> (provider, actual_model_id)
# Discovered from provider /models endpoints (see discover_models.py)
CODING: dict[str, tuple[str, str] | None] = {
    "auto": None,
    "fcm": None,
    # OpenRouter free
    "hy3": ("openrouter", "tencent/hy3:free"),
    "laguna-m1": ("openrouter", "poolside/laguna-m.1:free"),
    "laguna-xs": ("openrouter", "poolside/laguna-xs-2.1:free"),
    "gemma4-31b": ("openrouter", "google/gemma-4-31b-it:free"),
    "nemotron-super": ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    "nemotron-nano": ("openrouter", "nvidia/nemotron-3-nano-30b-a3b:free"),
    "qwen3-coder": ("openrouter", "qwen/qwen3-coder:free"),
    "llama-3.3-70b-free": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    "hermes-3-405b": ("openrouter", "nousresearch/hermes-3-llama-3.1-405b:free"),
    "gpt-oss-20b": ("openrouter", "openai/gpt-oss-20b:free"),
    # NVIDIA NIM direct (credit-based)
    "nim-nemotron-super": ("nvidia", "nvidia/nemotron-3-super-120b-a12b"),
    "nim-nemotron-nano": ("nvidia", "nvidia/nemotron-3-nano-30b-a3b"),
    "nim-llama-3.1-70b": ("nvidia", "meta/llama-3.1-70b-instruct"),
    "nim-llama-3.3-70b": ("nvidia", "meta/llama-3.3-70b-instruct"),
    "nim-qwen3.5-397b": ("nvidia", "qwen/qwen3.5-397b-a17b"),
    "nim-qwen3.5-122b": ("nvidia", "qwen/qwen3.5-122b-a10b"),
    "nim-deepseek-v4-flash": ("nvidia", "deepseek-ai/deepseek-v4-flash"),
    "nim-deepseek-v4-pro": ("nvidia", "deepseek-ai/deepseek-v4-pro"),
    "nim-mistral-large-3": ("nvidia", "mistralai/mistral-large-3-675b-instruct-2512"),
    "nim-gemma4-31b": ("nvidia", "google/gemma-4-31b-it"),
    "nim-glm5.2": ("nvidia", "z-ai/glm-5.2"),
    "nim-inkling": ("nvidia", "thinkingmachines/inkling"),
    # Google (via OpenAI-compat)
    "gemini-2.5-flash": ("google", "models/gemini-2.5-flash"),
    "gemini-2.5-flash-lite": ("google", "models/gemini-2.5-flash-lite"),
    "gemini-2.0-flash": ("google", "models/gemini-2.0-flash"),
    "gemma4-31b-google": ("google", "models/gemma-4-31b-it"),
    # Mistral
    "mistral-small": ("mistral", "mistral-small-latest"),
    "codestral": ("mistral", "codestral-latest"),
    "mistral-large": ("mistral", "mistral-large-latest"),
    "mistral-medium": ("mistral", "mistral-medium-latest"),
    # Groq (fast inference, free tier)
    "groq-llama-3.3-70b": ("groq", "llama-3.3-70b-versatile"),
    "groq-qwen3-32b": ("groq", "qwen/qwen3-32b"),
    "groq-qwen3.6-27b": ("groq", "qwen/qwen3.6-27b"),
    "groq-gpt-oss-120b": ("groq", "openai/gpt-oss-120b"),
    "groq-gpt-oss-20b": ("groq", "openai/gpt-oss-20b"),
    "groq-llama-4-scout": ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
}

PROVIDERS: dict[str, dict[str, str]] = {
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

AST_RE = re.compile(
    r"(def |class |import |from |function |const |let |var |#include|package |fn |pub |struct |impl |"
    r"async |await |\.ts|\.py|\.rs|\.js|AST|tree-sitter|syntax|```)",
    re.I,
)


# ---------------------------------------------------------------------------
# HealthDB - persistent model health tracking with healing detection
# ---------------------------------------------------------------------------
class HealthDB:
    """SQLite WAL DB for model health, latency, rate-limit, and healing events."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL    NOT NULL,
                provider    TEXT    NOT NULL,
                model       TEXT    NOT NULL,
                status      INTEGER NOT NULL,
                latency_ms  REAL    NOT NULL,
                strategy    TEXT    NOT NULL DEFAULT '',
                winner      INTEGER NOT NULL DEFAULT 0,
                session_id  TEXT    NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_req_prov_model ON requests(provider, model);
            CREATE INDEX IF NOT EXISTS idx_req_ts ON requests(ts);

            CREATE TABLE IF NOT EXISTS model_health (
                provider    TEXT    NOT NULL,
                model       TEXT    NOT NULL,
                window_start REAL   NOT NULL,
                successes   INTEGER NOT NULL DEFAULT 0,
                failures    INTEGER NOT NULL DEFAULT 0,
                rate_limited INTEGER NOT NULL DEFAULT 0,
                total_ms    REAL    NOT NULL DEFAULT 0,
                min_ms      REAL    NOT NULL DEFAULT 999999,
                max_ms      REAL    NOT NULL DEFAULT 0,
                PRIMARY KEY (provider, model, window_start)
            );

            CREATE TABLE IF NOT EXISTS healing_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL    NOT NULL,
                provider    TEXT    NOT NULL,
                model       TEXT    NOT NULL,
                event       TEXT    NOT NULL,
                prev_status TEXT    NOT NULL DEFAULT '',
                new_status  TEXT    NOT NULL DEFAULT '',
                details     TEXT    NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_heal_prov ON healing_events(provider, ts);

            CREATE TABLE IF NOT EXISTS rate_limit_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL    NOT NULL,
                provider    TEXT    NOT NULL,
                model       TEXT    NOT NULL,
                status_code INTEGER NOT NULL,
                retry_after REAL    DEFAULT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rl_prov_ts ON rate_limit_events(provider, ts);

            CREATE TABLE IF NOT EXISTS session_affinity (
                session_id  TEXT PRIMARY KEY,
                provider    TEXT NOT NULL,
                model       TEXT NOT NULL,
                updated_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_affinity_updated ON session_affinity(updated_at);
        """)
        self.conn.commit()

    def record_request(
        self,
        provider: str,
        model: str,
        status: int,
        latency_ms: float,
        strategy: str = "",
        winner: int = 0,
        session_id: str = "",
    ) -> None:
        now = time.time()
        window = now - (now % 300)
        self.conn.execute(
            "INSERT INTO requests"
            " (ts,provider,model,status,latency_ms,strategy,winner,session_id)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (now, provider, model, status, latency_ms, strategy, winner, session_id),
        )
        if status == 200:
            self.conn.execute(
                "INSERT INTO model_health"
                " (provider,model,window_start,successes,failures,total_ms,min_ms,max_ms)"
                " VALUES (?,?,?,1,0,?,?,?)"
                " ON CONFLICT(provider,model,window_start) DO UPDATE SET"
                " successes=successes+1, total_ms=total_ms+excluded.total_ms,"
                " min_ms=min(min_ms,excluded.min_ms),"
                " max_ms=max(max_ms,excluded.max_ms)",
                (provider, model, window, latency_ms, latency_ms, latency_ms),
            )
        elif status == 429:
            self.conn.execute(
                "INSERT INTO model_health"
                " (provider,model,window_start,successes,failures,rate_limited,total_ms,min_ms,max_ms)"
                " VALUES (?,?,?,0,0,1,?,?,?)"
                " ON CONFLICT(provider,model,window_start) DO UPDATE SET"
                " rate_limited=rate_limited+1",
                (provider, model, window, latency_ms, latency_ms, latency_ms),
            )
        else:
            self.conn.execute(
                "INSERT INTO model_health"
                " (provider,model,window_start,successes,failures,total_ms,min_ms,max_ms)"
                " VALUES (?,?,?,0,1,?,?,?)"
                " ON CONFLICT(provider,model,window_start) DO UPDATE SET"
                " failures=failures+1, total_ms=total_ms+excluded.total_ms,"
                " min_ms=min(min_ms,excluded.min_ms),"
                " max_ms=max(max_ms,excluded.max_ms)",
                (provider, model, window, latency_ms, latency_ms, latency_ms),
            )
        self.conn.commit()

    def record_rate_limit(
        self,
        provider: str,
        model: str,
        status_code: int,
        retry_after: float | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO rate_limit_events"
            " (ts,provider,model,status_code,retry_after)"
            " VALUES (?,?,?,?,?)",
            (time.time(), provider, model, status_code, retry_after),
        )
        self.conn.commit()

    def record_healing(
        self,
        provider: str,
        model: str,
        event: str,
        prev_status: str = "",
        new_status: str = "",
        details: str = "",
    ) -> None:
        self.conn.execute(
            "INSERT INTO healing_events"
            " (ts,provider,model,event,prev_status,new_status,details)"
            " VALUES (?,?,?,?,?,?,?)",
            (time.time(), provider, model, event, prev_status, new_status, details),
        )
        self.conn.commit()

    def get_health_score(
        self, provider: str, model: str, window_minutes: int = 30
    ) -> float:
        cutoff = time.time() - (window_minutes * 60)
        row = self.conn.execute(
            "SELECT SUM(successes), SUM(failures) FROM model_health"
            " WHERE provider=? AND model=? AND window_start>=?",
            (provider, model, cutoff),
        ).fetchone()
        if not row or (row[0] is None and row[1] is None):
            return 0.5
        s: int = row[0] or 0
        f: int = row[1] or 0
        total = s + f
        return s / total if total > 0 else 0.5

    def get_avg_latency(
        self, provider: str, model: str, window_minutes: int = 30
    ) -> float:
        cutoff = time.time() - (window_minutes * 60)
        row = self.conn.execute(
            "SELECT AVG(total_ms / (successes + failures)) FROM model_health"
            " WHERE provider=? AND model=? AND window_start>=?"
            " AND (successes + failures) > 0",
            (provider, model, cutoff),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else -1.0

    def get_recent_healing(
        self, provider: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT ts,model,event,prev_status,new_status,details"
            " FROM healing_events WHERE provider=?"
            " ORDER BY ts DESC LIMIT ?",
            (provider, limit),
        ).fetchall()
        return [
            {
                "ts": r[0],
                "model": r[1],
                "event": r[2],
                "prev": r[3],
                "new": r[4],
                "details": r[5],
            }
            for r in rows
        ]

    def get_provider_summary(self) -> dict[str, dict[str, Any]]:
        cutoff = time.time() - 1800
        rows = self.conn.execute(
            "SELECT provider, SUM(successes), SUM(failures),"
            " AVG(total_ms / max(successes+failures,1)),"
            " SUM(rate_limited) FROM model_health"
            " WHERE window_start>=? GROUP BY provider",
            (cutoff,),
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            prov: str = r[0]
            s: int = r[1] or 0
            f: int = r[2] or 0
            total = s + f
            result[prov] = {
                "successes": s,
                "failures": f,
                "success_rate": round(s / total, 3) if total > 0 else None,
                "avg_latency_ms": round(float(r[3]), 1) if r[3] is not None else None,
                "rate_limited": r[4] or 0,
            }
        return result

    def sticky_get(
        self, session_id: str, ttl: float = 1800
    ) -> tuple[str | None, str | None]:
        cutoff = time.time() - ttl
        row = self.conn.execute(
            "SELECT provider, model FROM session_affinity"
            " WHERE session_id=? AND updated_at>=?",
            (session_id, cutoff),
        ).fetchone()
        if row:
            return row[0], row[1]
        return None, None

    def sticky_set(self, session_id: str, provider: str, model: str) -> None:
        self.conn.execute(
            "INSERT INTO session_affinity(session_id, provider, model, updated_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(session_id) DO UPDATE SET"
            " provider=excluded.provider, model=excluded.model,"
            " updated_at=excluded.updated_at",
            (session_id, provider, model, time.time()),
        )
        self.conn.commit()

    def cleanup_old(self, days: int = 7) -> int:
        cutoff = time.time() - (days * 86400)
        c1 = self.conn.execute("DELETE FROM requests WHERE ts<?", (cutoff,)).rowcount
        c2 = self.conn.execute(
            "DELETE FROM model_health WHERE window_start<?", (cutoff,)
        ).rowcount
        c3 = self.conn.execute(
            "DELETE FROM healing_events WHERE ts<?", (cutoff,)
        ).rowcount
        c4 = self.conn.execute(
            "DELETE FROM rate_limit_events WHERE ts<?", (cutoff,)
        ).rowcount
        c5 = self.conn.execute(
            "DELETE FROM session_affinity WHERE updated_at<?",
            (time.time() - 86400,),
        ).rowcount
        self.conn.commit()
        return c1 + c2 + c3 + c4 + c5


# ---------------------------------------------------------------------------
# State: ELO, circuit breakers, sticky, FIFO, health DB
# ---------------------------------------------------------------------------
class Matrix:
    def __init__(self) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.fail: dict[str, tuple[int, float]] = {}
        self.elo: dict[str, float] = {p: 1000.0 for p in PROVIDERS}
        self.circuit: dict[str, str] = {p: "closed" for p in PROVIDERS}
        self.circuit_open_until: dict[str, float] = {}
        self.fifo: queue.Queue[int] = queue.Queue(maxsize=FIFO_MAX)
        self.health = HealthDB(DB)

    def record(
        self,
        model: str,
        prov: str,
        status: int,
        lat: float,
        winner: int = 0,
        strategy: str = "",
        session: str = "",
    ) -> None:
        lat_ms = lat * 1000
        with self.lock:
            self.health.record_request(
                prov,
                model,
                status,
                lat_ms,
                strategy,
                winner,
                session,
            )
            if status == 200:
                old_circuit = self.circuit.get(prov, "closed")
                self.elo[prov] = self.elo.get(prov, 1000) + 16
                self.fail[prov] = (0, time.time())
                self.circuit[prov] = "closed"
                if old_circuit != "closed":
                    self.health.record_healing(
                        prov,
                        model,
                        "circuit_recovered",
                        prev_status=old_circuit,
                        new_status="closed",
                    )
            elif status == 429:
                self.health.record_rate_limit(prov, model, status)
                self.elo[prov] = max(100.0, self.elo.get(prov, 1000) - 8)
                c, _ = self.fail.get(prov, (0, 0))
                self.fail[prov] = (c + 1, time.time())
            else:
                c, _ = self.fail.get(prov, (0, 0))
                self.fail[prov] = (c + 1, time.time())
                self.elo[prov] = max(100.0, self.elo.get(prov, 1000) - 32)
                if c + 1 >= 3:
                    old = self.circuit.get(prov, "closed")
                    self.circuit[prov] = "open"
                    self.circuit_open_until[prov] = time.time() + 60
                    self.health.record_healing(
                        prov,
                        model,
                        "circuit_opened",
                        prev_status=old,
                        new_status="open",
                        details=f"{c + 1} consecutive failures",
                    )

    def sticky_get(self, sid: str) -> tuple[str | None, str | None]:
        return self.health.sticky_get(sid, STICKY_TTL)

    def sticky_set(self, sid: str, p: str, m: str) -> None:
        self.health.sticky_set(sid, p, m)

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
    conf = PROVIDERS[p]
    env: str = conf.get("key_env", "")
    alt: str = conf.get("key_env_alt", "")
    return os.getenv(env, "") or (os.getenv(alt, "") if alt else "") or ""


def key_ok(p: str) -> bool:
    return bool(get_key(p))


def first_model_for(p: str) -> str:
    models = PROVIDER_MODELS.get(p, [])
    return models[0] if models else ""


def resolve_model(model: str) -> tuple[str, str]:
    if model in CODING and CODING[model] is not None:
        pair = CODING[model]
        assert pair is not None
        return pair
    if model in ("auto", "fcm"):
        for p in ("openrouter", "nvidia", "groq", "cerebras", "google", "mistral"):
            if key_ok(p):
                mid = first_model_for(p)
                if mid:
                    return p, mid
        return "openrouter", "tencent/hy3:free"
    for p, models in PROVIDER_MODELS.items():
        if model in models:
            return p, model
    if key_ok("openrouter"):
        return "openrouter", model
    if key_ok("nvidia"):
        return "nvidia", model
    return "openrouter", "tencent/hy3:free"


def is_ast(text: str) -> bool:
    return bool(text and (AST_RE.search(text[:5000]) or "```" in text))


# ---------------------------------------------------------------------------
# Provider call - supports streaming
# ---------------------------------------------------------------------------
def call_one(provider: str, model: str, body: ChatBody) -> RouteResult:
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
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_key(provider)}",
        "User-Agent": "Mozilla/5.0 (compatible; SovereignASTMatrix/3.1)",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://zed.dev"
        headers["X-Title"] = "Sovereign-AST-Matrix"
    start = time.time()
    try:
        req = Request(url, data=data, headers=headers, method="POST")
        resp = urlopen(req, timeout=120)
        lat = time.time() - start
        is_stream: bool = body.get("stream", False)
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


def call_one_stream(provider: str, model: str, body: ChatBody) -> RouteResult:
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
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_key(provider)}",
        "User-Agent": "Mozilla/5.0 (compatible; SovereignASTMatrix/3.1)",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://zed.dev"
        headers["X-Title"] = "Sovereign-AST-Matrix"
    stream_body: ChatBody = {**body, "model": model, "stream": True}
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
def pick_weighted(n: int = MAX_PARALLEL) -> list[tuple[str, str]]:
    scored: list[tuple[float, str, str]] = []
    for p in PROVIDERS:
        if not key_ok(p) or not state.circuit_ok(p):
            continue
        sc = state.elo.get(p, 1000) + random.random() * 10
        mid = first_model_for(p)
        if mid:
            scored.append((sc, p, mid))
    scored.sort(reverse=True)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _, p, mid in scored:
        if p not in seen:
            seen.add(p)
            out.append((p, mid))
        if len(out) >= n:
            break
    if not out and key_ok("openrouter"):
        out = [("openrouter", "tencent/hy3:free")]
    return out


# ---------------------------------------------------------------------------
# Strategy routes
# ---------------------------------------------------------------------------
def route_ast_race(body: ChatBody, session: str) -> RouteResult:
    model = body.get("model", "auto")
    # FIX: Explicit model -> route to THAT provider only, no race, no fallthrough
    if model in CODING and CODING[model] is not None:
        pair = CODING[model]
        assert pair is not None
        p, mid = pair
        r = call_one(p, mid, body)
        if r.get("ok"):
            state.sticky_set(session, p, mid)
            state.record(mid, p, 200, r["lat"], winner=1, strategy="ast_race")
        return r
    # auto/fcm/unknown: race across providers
    cands = pick_weighted(MAX_PARALLEL)
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
        futs = {ex.submit(call_one, p, mid, body): (p, mid) for p, mid in cands}
        best: RouteResult | None = None
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
        if best is not None:
            state.sticky_set(session, best["provider"], best["model"])
            return best
    return {"ok": False, "status": 503, "err": "ast_race_exhausted"}


def route_sticky(body: ChatBody, session: str) -> RouteResult:
    model = body.get("model", "auto")
    # FIX: Explicit model -> skip sticky, go direct
    if model in CODING and CODING[model] is not None:
        return route_ast_race(body, session)
    p, m = state.sticky_get(session)
    if p is not None and key_ok(p) and state.circuit_ok(p):
        r = call_one(p, m or model, body)
        if r.get("ok"):
            return r
    return route_ast_race(body, session)


def route_weighted(body: ChatBody, session: str) -> RouteResult:
    cands = pick_weighted(1)
    if not cands:
        return {"ok": False, "status": 503, "err": "no_providers"}
    p, mid = cands[0]
    r = call_one(p, mid, body)
    if r.get("ok"):
        state.sticky_set(session, p, mid)
    return r


def route_circuit_chain(body: ChatBody, session: str) -> RouteResult:
    model = body.get("model", "auto")
    # FIX: Explicit model -> try only that provider, don't cascade
    if model in CODING and CODING[model] is not None:
        pair = CODING[model]
        assert pair is not None
        p, mid = pair
        if key_ok(p) and state.circuit_ok(p):
            r = call_one(p, mid, body)
            if r.get("ok"):
                state.sticky_set(session, p, mid)
                return r
        return {"ok": False, "status": 502, "err": f"explicit_provider_unavailable:{p}"}
    # auto/fcm: cascade by ELO
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


def route_fifo(body: ChatBody, session: str) -> RouteResult:
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


def route_hybrid(body: ChatBody, session: str) -> RouteResult:
    model = body.get("model", "auto")
    # FIX: Explicit model -> resolve once, call directly, no sticky/cascade
    if model in CODING and CODING[model] is not None:
        p, mid = resolve_model(model)
        r = call_one(p, mid, body)
        if r.get("ok"):
            state.sticky_set(session, p, mid)
            state.record(mid, p, 200, r["lat"], winner=1, strategy="hybrid_direct")
            return r
        return r
    # auto/fcm: sticky -> ast_race -> circuit_chain
    p, m = state.sticky_get(session)
    if p is not None and key_ok(p) and state.circuit_ok(p):
        r = call_one(p, m or model, body)
        if r.get("ok"):
            return r
    r2 = route_ast_race(body, session)
    if r2.get("ok"):
        return r2
    return route_circuit_chain(body, session)


ROUTERS: dict[str, Any] = {
    "fifo_matrix": route_fifo,
    "ast_race": route_ast_race,
    "sticky_affinity": route_sticky,
    "weighted_elo": route_weighted,
    "circuit_chain": route_circuit_chain,
    "hybrid": route_hybrid,
}


# ---------------------------------------------------------------------------
# Streaming SSE proxy
# ---------------------------------------------------------------------------
def proxy_stream(
    resp: Any,
    handler: "H",
    provider: str,
    model: str,
) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Routed-Via", f"{provider}/{model}")
    handler.end_headers()
    try:
        while True:
            chunk: bytes = resp.read(4096)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        resp.close()


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        import sys
        print(f"[matrix] {format % args}", file=sys.stderr)

    def do_GET(self) -> None:
        if self.path in ("/v1/models", "/models"):
            ms: list[dict[str, str]] = [{"id": k, "object": "model"} for k in CODING]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"object": "list", "data": ms}).encode())
        elif self.path == "/health":
            key_status: dict[str, str] = {}
            for p in PROVIDERS:
                key_status[p] = "configured" if key_ok(p) else "no_key"
            # Merge DB health scores
            db_summary = state.health.get_provider_summary()
            providers_data: dict[str, dict[str, Any]] = {}
            for p in PROVIDERS:
                pd: dict[str, Any] = {
                    "keys": key_status[p],
                    "elo": round(state.elo.get(p, 1000), 1),
                    "circuit": state.circuit.get(p, "unknown"),
                    "models": len(PROVIDER_MODELS.get(p, [])),
                }
                if p in db_summary:
                    pd["health"] = db_summary[p]
                providers_data[p] = pd
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "status": "ok",
                        "router": "sovereign-ast-matrix",
                        "version": "v3.1",
                        "strategy": STRATEGY,
                        "parallel": MAX_PARALLEL,
                        "providers": providers_data,
                    }
                ).encode()
            )
        elif self.path == "/debug/sqlite":
            try:
                rows = state.health.conn.execute(
                    "SELECT model, provider, status, count(*), avg(latency_ms)"
                    " FROM requests GROUP BY model, provider, status"
                    " ORDER BY count(*) DESC LIMIT 20"
                ).fetchall()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        elif self.path == "/debug/health":
            try:
                summary = state.health.get_provider_summary()
                healing: dict[str, list[dict[str, Any]]] = {}
                for p in PROVIDERS:
                    healing[p] = state.health.get_recent_healing(p)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "summary": summary,
                            "healing": healing,
                        }
                    ).encode()
                )
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if "/chat/completions" not in self.path:
            self.send_response(404)
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0))
        body: ChatBody = json.loads(self.rfile.read(n) or b"{}")
        sid = (
            self.headers.get("X-Session-Id")
            or hashlib.md5(
                json.dumps(body.get("messages", [])[:1]).encode()
            ).hexdigest()[:12]
        )
        strat = self.headers.get("X-Sovereign-Strategy", STRATEGY)
        is_stream: bool = body.get("stream", False)
        if is_stream:
            self._handle_stream(body, sid, strat)
        else:
            self._handle_sync(body, sid, strat)

    def _handle_sync(self, body: ChatBody, sid: str, strat: str) -> None:
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

    def _handle_stream(self, body: ChatBody, sid: str, strat: str) -> None:
        model = body.get("model", "auto")
        # FIX: Explicit model -> skip sticky, route to correct provider
        if model in CODING and CODING[model] is not None:
            pair = CODING[model]
            assert pair is not None
            p, mid = pair
            r = call_one_stream(p, mid, body)
            if r.get("ok"):
                state.sticky_set(sid, p, mid)
                proxy_stream(r["resp"], self, p, mid)
                return
        else:
            # auto/fcm: try sticky first
            sp, sm = state.sticky_get(sid)
            if sp is not None and key_ok(sp) and state.circuit_ok(sp):
                r = call_one_stream(sp, sm or model, body)
                if r.get("ok"):
                    state.sticky_set(sid, sp, r["model"])
                    proxy_stream(r["resp"], self, sp, r["model"])
                    return
        candidates: list[tuple[str, str]] = []
        if model in CODING and CODING[model] is not None:
            pair = CODING[model]
            assert pair is not None
            candidates = [pair]
        else:
            candidates = pick_weighted(MAX_PARALLEL)
        for p, mid in candidates:
            r = call_one_stream(p, mid, body)
            if r.get("ok"):
                state.sticky_set(sid, p, mid)
                proxy_stream(r["resp"], self, p, mid)
                return
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"error": "all_stream_providers_exhausted"}).encode()
        )


def main() -> None:
    print(f"Sovereign AST Matrix v3.1 on http://127.0.0.1:{PORT}/v1")
    print(
        f"Strategy={STRATEGY} | 5 routes: fifo_matrix, ast_race, sticky_affinity,"
        f" weighted_elo, circuit_chain (+ hybrid)"
    )
    print(
        f"Streaming=SSE proxy | Providers: {', '.join(p for p in PROVIDERS if key_ok(p))}"
    )
    print(
        "No local GPU. Cloud-only: NVIDIA NIM + OpenRouter + Groq + Cerebras + Google + Mistral"
    )
    print(f"Health DB: {DB} (WAL mode)")

    # Periodic cleanup every hour
    def _cleanup() -> None:
        while True:
            time.sleep(3600)
            _ = state.health.cleanup_old(days=7)

    t = threading.Thread(target=_cleanup, daemon=True)
    t.start()
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
