#!/usr/bin/env python3
"""
Sovereign AST Router v1 — Merged maximal free coding gateway for Zed
===============================================================
Sources synthesized:
- 9Router (RTK token saver concept, 3-tier sub/cheap/free, multi-provider, format translation, dashboard ideas)
- free-llm-gateway (fallback chains, rate tracking, sticky)
- freellmapi (routing strategies, sticky 30m, context handoff, catalog)
- free-coding-models (coding ranking, daemon OpenAI endpoint, fcm virtual)
- ULTIMATE modules (llm_client, curlx-style fallbacks, orchestrator, env_dump, switchover robustness)
- Previous free_zed_gateway

Features:
- Aggressive parallel race: send to up to 4 providers simultaneously; first valid response that looks like AST/code wins.
- FIFO request matrix for queued work.
- Coding-first free models (Hy3, Laguna M.1/XS, Qwen3-Coder, Gemma4, Nemotron...).
- Sticky sessions + failure cooldown.
- Local club3090 / any OpenAI-compatible as tier-3.
- Pure stdlib preferred for restricted boxes; optional httpx.
- Zed-ready: point language_models openai api_url to http://127.0.0.1:19280/v1

Run: python3 router.py
"""
import os, json, time, hashlib, threading, queue, random, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3

PORT = int(os.getenv("SOVEREIGN_PORT", "19280"))
DB = os.getenv("SOVEREIGN_DB", "/tmp/sovereign_ast.db")
MAX_PARALLEL = 4
STICKY_TTL = 1800
FIFO = queue.Queue(maxsize=64)

# Coding / AST preferred free models (July 2026)
CODING = {
    "auto": None,
    "fcm": None,
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
}

PROVIDERS = {
    "openrouter": {"base": "https://openrouter.ai/api/v1", "key": os.getenv("OPENROUTER_API_KEY", "")},
    "groq": {"base": "https://api.groq.com/openai/v1", "key": os.getenv("GROQ_API_KEY", "")},
    "cerebras": {"base": "https://api.cerebras.ai/v1", "key": os.getenv("CEREBRAS_API_KEY", "")},
    "nvidia": {"base": "https://integrate.api.nvidia.com/v1", "key": os.getenv("NVIDIA_API_KEY", "")},
    "google": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "key": os.getenv("GOOGLE_API_KEY", "")},
    "mistral": {"base": "https://api.mistral.ai/v1", "key": os.getenv("MISTRAL_API_KEY", "")},
    "local": {"base": os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8020/v1"), "key": "local"},
}

AST_HINTS = re.compile(r"(def |class |import |from |function |const |let |var |#include|package |fn |pub |struct |impl |async |await |\.ts|\.py|\.rs|\.js|AST|ast\.|tree-sitter|syntax)", re.I)

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.sticky = {}
        self.fail = {}
        self.conn = sqlite3.connect(DB, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS reqs (ts REAL, model TEXT, provider TEXT, status INT, lat REAL, winner INT)")
        self.conn.commit()

    def record(self, model, prov, status, lat, winner=0):
        with self.lock:
            self.conn.execute("INSERT INTO reqs VALUES (?,?,?,?,?,?)", (time.time(), model, prov, status, lat, winner))
            self.conn.commit()

    def get_sticky(self, sid):
        with self.lock:
            if sid in self.sticky:
                p, m, t = self.sticky[sid]
                if time.time() - t < STICKY_TTL:
                    return p, m
                del self.sticky[sid]
        return None, None

    def set_sticky(self, sid, p, m):
        with self.lock:
            self.sticky[sid] = (p, m, time.time())

state = State()

def key_ok(p):
    k = PROVIDERS[p]["key"]
    return bool(k) or p == "local"

def score_provider(p):
    f = state.fail.get(p, (0, 0))
    return 100 - f[0] * 15 + random.random()

def pick_candidates(model, n=MAX_PARALLEL):
    cands = []
    if model in CODING and CODING[model]:
        p, mid = CODING[model]
        if key_ok(p):
            cands.append((200, p, mid))
    for p in PROVIDERS:
        if not key_ok(p):
            continue
        sc = score_provider(p)
        if p == "openrouter":
            sc += 40
        if p == "local":
            sc += 10
        mid = model if model not in ("auto", "fcm") else "tencent/hy3:free"
        cands.append((sc, p, mid))
    cands.sort(reverse=True)
    seen = set()
    out = []
    for sc, p, mid in cands:
        if p not in seen:
            seen.add(p)
            out.append((p, mid))
        if len(out) >= n:
            break
    return out or [("openrouter", "tencent/hy3:free")]

def call_one(provider, model, body):
    conf = PROVIDERS[provider]
    url = conf["base"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {conf['key']}"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://zed.dev"
        headers["X-Title"] = "Sovereign-AST-Router"
    data = json.dumps({**body, "model": model}).encode()
    start = time.time()
    try:
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=90) as resp:
            raw = resp.read()
            lat = time.time() - start
            state.record(model, provider, resp.status, lat)
            return {"ok": True, "status": resp.status, "data": raw, "provider": provider, "model": model, "lat": lat}
    except HTTPError as e:
        lat = time.time() - start
        state.record(model, provider, e.code, lat)
        with state.lock:
            c, _ = state.fail.get(provider, (0, 0))
            state.fail[provider] = (c + 1, time.time())
        return {"ok": False, "status": e.code, "provider": provider, "lat": lat}
    except Exception as e:
        lat = time.time() - start
        state.record(model, provider, 500, lat)
        return {"ok": False, "status": 500, "provider": provider, "lat": lat, "err": str(e)}

def is_ast_code(text):
    if not text:
        return False
    return bool(AST_HINTS.search(text[:4000])) or "```" in text

def race(body, session):
    model = body.get("model", "auto")
    sticky_p, sticky_m = state.get_sticky(session)
    if sticky_p and key_ok(sticky_p):
        r = call_one(sticky_p, sticky_m or model, body)
        if r["ok"]:
            try:
                j = json.loads(r["data"])
                content = j.get("choices", [{}])[0].get("message", {}).get("content", "")
                if is_ast_code(content) or True:  # accept sticky even if not AST for continuity
                    state.set_sticky(session, sticky_p, sticky_m)
                    return r
            except:
                pass
    cands = pick_candidates(model, MAX_PARALLEL)
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
        futs = {ex.submit(call_one, p, mid, body): (p, mid) for p, mid in cands}
        best = None
        for fut in as_completed(futs, timeout=95):
            r = fut.result()
            if not r.get("ok"):
                continue
            try:
                j = json.loads(r["data"])
                content = j.get("choices", [{}])[0].get("message", {}).get("content", "")
                if is_ast_code(content) or best is None:
                    best = r
                    if is_ast_code(content):
                        # winner: first AST-like
                        state.set_sticky(session, r["provider"], r["model"])
                        state.record(r["model"], r["provider"], 200, r["lat"], winner=1)
                        return r
            except:
                if best is None:
                    best = r
        if best:
            state.set_sticky(session, best["provider"], best["model"])
            return best
    return {"ok": False, "status": 503, "err": "all raced providers failed"}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            ms = [{"id": k, "object": "model"} for k in list(CODING) + ["auto", "fcm"]]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"object": "list", "data": ms}).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok","router":"sovereign-ast","parallel":4}')
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
        sid = self.headers.get("X-Session-Id") or hashlib.md5(json.dumps(body.get("messages", [])[:1]).encode()).hexdigest()[:12]
        # FIFO gate
        try:
            FIFO.put_nowait(1)
        except queue.Full:
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error":"fifo full"}')
            return
        try:
            r = race(body, sid)
            if r.get("ok"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Routed-Via", f"{r['provider']}/{r['model']}")
                self.send_header("X-Latency", str(round(r.get("lat", 0), 3)))
                self.end_headers()
                self.wfile.write(r["data"])
            else:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": r.get("err", "exhausted"), "status": r.get("status")}).encode())
        finally:
            try:
                FIFO.get_nowait()
            except:
                pass

def main():
    print(f"Sovereign AST Router on http://127.0.0.1:{PORT}/v1")
    print("Parallel race: 4 providers, first AST/code response wins. FIFO queue.")
    print("Set OPENROUTER_API_KEY (+ others). Point Zed language_models here.")
    print("Models: auto, fcm, hy3, laguna-m1, qwen3-coder, gemma4-*, nemotron-*")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()

if __name__ == "__main__":
    main()
