#!/usr/bin/env bun
/**
 * Sovereign Router v3.1 (Bun/TypeScript)
 * Port of sovereign-router/router.py — same strategies, HealthDB WAL, circuit breakers.
 *
 * Strategies: fifo_matrix | ast_race | sticky_affinity | weighted_elo | circuit_chain | hybrid
 * Default hybrid: sticky → ast_race → circuit_chain; explicit CODING aliases go direct.
 *
 * Env SSOT: sovereign/config/ports.env (mise _.file) + ~/.secrets
 *   SOVEREIGN_ROUTER_PORT / SOVEREIGN_PORT — never invent non-25xxx ports
 */

import { Database } from "bun:sqlite";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname } from "node:path";
import { handleMeshRequest } from "../../../src/lib/ghas-mesh-features.ts";

// ---------------------------------------------------------------------------
// Secrets + local stack env (mise loads these; standalone bun needs them too)
// ---------------------------------------------------------------------------
function loadEnvFile(path: string): void {
  if (!existsSync(path)) return;
  try {
    for (let line of readFileSync(path, "utf8").split("\n")) {
      line = line.trim();
      if (!line || line.startsWith("#")) continue;
      if (line.startsWith("export ")) line = line.slice(7);
      const eq = line.indexOf("=");
      if (eq < 1) continue;
      const k = line.slice(0, eq).trim();
      let v = line
        .slice(eq + 1)
        .trim()
        .replace(/^['"]|['"]$/g, "");
      if (k && v && !process.env[k]) process.env[k] = v;
    }
  } catch (e) {
    console.error(`[matrix] loadEnvFile ${path}:`, e);
  }
}
loadEnvFile(`${homedir()}/.secrets`);
loadEnvFile("/home/toxic/.secrets");
loadEnvFile("/home/toxic/sovereign/config/ports.env");
loadEnvFile("/home/toxic/sovereign/.env.local");

// Port SSOT: process-compose injects SOVEREIGN_PORT=${SOVEREIGN_ROUTER_PORT}
const _portRaw =
  process.env.SOVEREIGN_PORT || process.env.SOVEREIGN_ROUTER_PORT || "";
if (!_portRaw) {
  throw new Error(
    "SOVEREIGN_ROUTER_PORT or SOVEREIGN_PORT required (config/ports.env)",
  );
}
const PORT = parseInt(_portRaw, 10);
const DB_PATH =
  process.env.SOVEREIGN_DB || "/home/toxic/sovereign/data/sovereign_router.db";
const MAX_PARALLEL = 4;
const STICKY_TTL = 1800;
const FIFO_MAX = 64;
const STRATEGY = process.env.SOVEREIGN_STRATEGY || "hybrid";
const UA = "Mozilla/5.0 (compatible; SovereignASTMatrix/3.1)";

// ---------------------------------------------------------------------------
// LLAMA_SWAP_V1 (must come before PROVIDERS that uses it)
// ---------------------------------------------------------------------------
const LLAMA_SWAP_V1 =
  process.env.LLM_BASE_URL ||
  process.env.LLAMA_SWAP_V1 ||
  "http://127.0.0.1:25100/v1";

// ---------------------------------------------------------------------------
// Local role models (must come before PROVIDER_MODELS that depends on it)
// ---------------------------------------------------------------------------
/** Load ranked local roles from llama-swap SSOT file if present. */
function loadLocalRoleModels(): {
  fast: string;
  quality: string;
  longctx: string;
} {
  const defaults = {
    fast: "beellama/exaone-4-0-1-2b-iq4xs",
    quality: "beellama/qwen-flash-64k",
    longctx: "beellama/qwen-flash-256k",
  };
  try {
    const p = "/home/toxic/sovereign/.state/best-models.json";
    if (!existsSync(p)) return defaults;
    const j = JSON.parse(readFileSync(p, "utf8"));
    return {
      fast: j?.roles?.fast?.id || j?.recommended?.preload || defaults.fast,
      quality:
        j?.roles?.quality?.id ||
        j?.recommended?.default_chat ||
        defaults.quality,
      longctx:
        j?.roles?.longctx?.id ||
        j?.recommended?.long_context ||
        defaults.longctx,
    };
  } catch {
    return defaults;
  }
}
const LOCAL_ROLES = loadLocalRoleModels();

// ---------------------------------------------------------------------------
// Providers (must come before Catalog that depends on LOCAL_ROLES)
// ---------------------------------------------------------------------------
const PROVIDERS: Record<
  string,
  { base: string; key_env: string; key_env_alt?: string; no_auth?: boolean }
> = {
  // Local SSOT — always first-class for sovereign GPU path
  "llama-swap": {
    base: LLAMA_SWAP_V1,
    key_env: "LLAMA_SWAP_API_KEY",
    no_auth: true,
  },
  openrouter: {
    base: "https://openrouter.ai/api/v1",
    key_env: "OPENROUTER_API_KEY",
  },
  nvidia: {
    base: "https://integrate.api.nvidia.com/v1",
    key_env: "NVIDIA_API_KEY",
    key_env_alt: "NVIDIA_NIM_API_KEY",
  },
  groq: { base: "https://api.groq.com/openai/v1", key_env: "GROQ_API_KEY" },
  cerebras: {
    base: "https://api.cerebras.ai/v1",
    key_env: "CEREBRAS_API_KEY",
  },
  google: {
    base: "https://generativelanguage.googleapis.com/v1beta/openai",
    key_env: "GOOGLE_API_KEY",
  },
  mistral: { base: "https://api.mistral.ai/v1", key_env: "MISTRAL_API_KEY" },
};

// ---------------------------------------------------------------------------
// Catalog (depends on LOCAL_ROLES, must come after loadLocalRoleModels)
// ---------------------------------------------------------------------------
const PROVIDER_MODELS: Record<string, string[]> = {
  "llama-swap": [LOCAL_ROLES.fast, LOCAL_ROLES.quality, LOCAL_ROLES.longctx],
  openrouter: [
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
  nvidia: [
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
  groq: [
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
  ],
  cerebras: [],
  google: [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.0-flash",
    "models/gemma-4-31b-it",
  ],
  mistral: [
    "mistral-small-latest",
    "codestral-latest",
    "mistral-large-latest",
    "mistral-medium-latest",
  ],
};

/** Friendly alias → [provider, model_id] | null for auto/fcm */
/** Load ranked local roles from llama-swap SSOT file if present. */
function loadLocalRoleModels(): {
  fast: string;
  quality: string;
  longctx: string;
} {
  const defaults = {
    fast: "beellama/exaone-4-0-1-2b-iq4xs",
    quality: "beellama/qwen-flash-64k",
    longctx: "beellama/qwen-flash-256k",
  };
  try {
    const p = "/home/toxic/sovereign/.state/best-models.json";
    if (!existsSync(p)) return defaults;
    const j = JSON.parse(readFileSync(p, "utf8"));
    return {
      fast: j?.roles?.fast?.id || j?.recommended?.preload || defaults.fast,
      quality:
        j?.roles?.quality?.id ||
        j?.recommended?.default_chat ||
        defaults.quality,
      longctx:
        j?.roles?.longctx?.id ||
        j?.recommended?.long_context ||
        defaults.longctx,
    };
  } catch {
    return defaults;
  }
}
const CODING: Record<string, [string, string] | null> = {
  auto: null,
  fcm: null,
  // free: route through the `free` strategy (local + all :free cloud models)
  free: null,
  // Local-first ranked roles (llama-swap exclusive matrix)
  fast: ["llama-swap", LOCAL_ROLES.fast],
  "local-fast": ["llama-swap", LOCAL_ROLES.fast],
  quality: ["llama-swap", LOCAL_ROLES.quality],
  "local-quality": ["llama-swap", LOCAL_ROLES.quality],
  longctx: ["llama-swap", LOCAL_ROLES.longctx],
  "local-longctx": ["llama-swap", LOCAL_ROLES.longctx],
  "local-auto": ["llama-swap", LOCAL_ROLES.quality],
  hy3: ["openrouter", "tencent/hy3:free"],
  "laguna-m1": ["openrouter", "poolside/laguna-m.1:free"],
  "laguna-xs": ["openrouter", "poolside/laguna-xs-2.1:free"],
  "gemma4-31b": ["openrouter", "google/gemma-4-31b-it:free"],
  "nemotron-super": ["openrouter", "nvidia/nemotron-3-super-120b-a12b:free"],
  "nemotron-nano": ["openrouter", "nvidia/nemotron-3-nano-30b-a3b:free"],
  "qwen3-coder": ["openrouter", "qwen/qwen3-coder:free"],
  "llama-3.3-70b-free": [
    "openrouter",
    "meta-llama/llama-3.3-70b-instruct:free",
  ],
  "hermes-3-405b": ["openrouter", "nousresearch/hermes-3-llama-3.1-405b:free"],
  "gpt-oss-20b": ["openrouter", "openai/gpt-oss-20b:free"],
  "nim-nemotron-super": ["nvidia", "nvidia/nemotron-3-super-120b-a12b"],
  "nim-nemotron-nano": ["nvidia", "nvidia/nemotron-3-nano-30b-a3b"],
  "nim-llama-3.1-70b": ["nvidia", "meta/llama-3.1-70b-instruct"],
  "nim-llama-3.3-70b": ["nvidia", "meta/llama-3.3-70b-instruct"],
  "nim-qwen3.5-397b": ["nvidia", "qwen/qwen3.5-397b-a17b"],
  "nim-qwen3.5-122b": ["nvidia", "qwen/qwen3.5-122b-a10b"],
  "nim-deepseek-v4-flash": ["nvidia", "deepseek-ai/deepseek-v4-flash"],
  "nim-deepseek-v4-pro": ["nvidia", "deepseek-ai/deepseek-v4-pro"],
  "nim-mistral-large-3": [
    "nvidia",
    "mistralai/mistral-large-3-675b-instruct-2512",
  ],
  "nim-gemma4-31b": ["nvidia", "google/gemma-4-31b-it"],
  "nim-glm5.2": ["nvidia", "z-ai/glm-5.2"],
  "nim-inkling": ["nvidia", "thinkingmachines/inkling"],
  "gemini-2.5-flash": ["google", "models/gemini-2.5-flash"],
  "gemini-2.5-flash-lite": ["google", "models/gemini-2.5-flash-lite"],
  "gemini-2.0-flash": ["google", "models/gemini-2.0-flash"],
  "gemma4-31b-google": ["google", "models/gemma-4-31b-it"],
  "mistral-small": ["mistral", "mistral-small-latest"],
  codestral: ["mistral", "codestral-latest"],
  "mistral-large": ["mistral", "mistral-large-latest"],
  "mistral-medium": ["mistral", "mistral-medium-latest"],
  "groq-llama-3.3-70b": ["groq", "llama-3.3-70b-versatile"],
  "groq-qwen3-32b": ["groq", "qwen/qwen3-32b"],
  "groq-qwen3.6-27b": ["groq", "qwen/qwen3.6-27b"],
  "groq-gpt-oss-120b": ["groq", "openai/gpt-oss-120b"],
  "groq-gpt-oss-20b": ["groq", "openai/gpt-oss-20b"],
  "groq-llama-4-scout": ["groq", "meta-llama/llama-4-scout-17b-16e-instruct"],
};

const AST_RE =
  /(def |class |import |from |function |const |let |var |#include|package |fn |pub |struct |impl |async |await |\.ts|\.py|\.rs|\.js|AST|tree-sitter|syntax|```)/i;

// ---------------------------------------------------------------------------
// UI dashboard (self-contained HTML at /ui)
// ---------------------------------------------------------------------------
function uiData(): Record<string, unknown> {
  const providers: Record<string, unknown> = {};
  for (const name of Object.keys(PROVIDERS)) {
    const free = (PROVIDER_MODELS[name] || []).filter((m) =>
      m.includes(":free"),
    );
    providers[name] = {
      keyed: keyOk(name),
      circuit: state.circuit.get(name) || "unknown",
      elo: Math.round((state.elo.get(name) || 1000) * 10) / 10,
      models: (PROVIDER_MODELS[name] || []).length,
      free_models: free,
    };
  }
  return {
    router: "sovereign-router-ts",
    version: "v3.1",
    strategy: STRATEGY,
    providers,
  };
}

const ROUTER_UI_HTML = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Sovereign Router — Provider Matrix</title>
<style>
:root{--bg:#0b0e14;--panel:#121826;--panel2:#0f1420;--ink:#e6edf3;--muted:#8b98a9;--acc:#5ad1c4;--free:#7ee787;--warn:#f0883e;--bad:#ff6b6b;--line:#1f2937}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--bg);color:var(--ink)}
header{padding:18px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
header h1{font-size:18px;margin:0;letter-spacing:.5px}header .sub{color:var(--muted);font-size:12px}
.wrap{display:grid;grid-template-columns:1.1fr .9fr;gap:16px;padding:18px 22px}
@media(max-width:900px){.wrap{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.panel h2{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--acc)}
.prov{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:8px;margin-bottom:8px;background:var(--panel2)}
.prov .name{font-weight:600}.chip{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line)}
.chip.ok{color:var(--free);border-color:#234d2b}.chip.no{color:var(--muted);border-color:#2a3340}
.chip.open{color:var(--bad);border-color:#4d2326}.chip.half{color:var(--warn);border-color:#4d3a23}
.tag{font-size:11px;padding:2px 7px;border-radius:6px;background:#0c111b;border:1px solid var(--line);color:var(--muted)}
.tag.free{color:var(--free);border-color:#234d2b}.tag.local{color:var(--acc);border-color:#1d3b39}
textarea,input,select{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:9px;font:inherit}
textarea{min-height:90px;resize:vertical}.row{display:flex;gap:8px;margin-bottom:8px}
button{background:var(--acc);color:#04201d;border:0;border-radius:8px;padding:9px 14px;font-weight:700;cursor:pointer}
pre{background:#06090f;border:1px solid var(--line);border-radius:8px;padding:10px;max-height:320px;overflow:auto;white-space:pre-wrap;word-break:break-word;margin:10px 0 0}
.meta{color:var(--muted);font-size:12px;margin-top:6px}
</style></head>
<body><header><h1>Sovereign Router</h1><span class="sub" id="sub">loading</span></header>
<div class="wrap"><div class="panel"><h2>Provider Matrix</h2><div id="providers"><span class="meta">loading</span></div></div>
<div class="panel"><h2>Chat (OpenAI-compatible)</h2>
<div class="row"><select id="model"></select>
<select id="strategy"><option value="hybrid">hybrid</option><option value="free">free (local+free cloud)</option><option value="ast_race">ast_race</option><option value="sticky_affinity">sticky_affinity</option><option value="weighted_elo">weighted_elo</option><option value="circuit_chain">circuit_chain</option><option value="fifo_matrix">fifo_matrix</option></select></div>
<textarea id="prompt" placeholder="Ask anything">Hello, identify which model is answering.</textarea>
<div class="row" style="margin-top:8px"><button id="send">Send</button><button id="stream" style="background:var(--panel2);color:var(--ink);border:1px solid var(--line)">Stream</button></div>
<pre id="out">-</pre><div class="meta" id="routed"></div></div></div>
<script>
const api=(p,o)=>fetch(p,o).then(r=>r.json()).catch(e=>({error:String(e)}));
async function load(){
 const h=await api('/health');
 document.getElementById('sub').textContent='v'+(h.version||'?')+' - strategy='+(h.strategy||'?')+' - '+Object.keys(h.providers||{}).length+' providers';
 const sel=document.getElementById('model');const prov=document.getElementById('providers');prov.innerHTML='';
 for(const [name,p] of Object.entries(h.providers||{})){
  const keyed=p.keys==='configured';const circ=(p.circuit||'unknown');
  const cc=circ==='closed'?'ok':(circ==='open'?'open':(circ==='half'?'half':'no'));
  const el=document.createElement('div');el.className='prov';
  el.innerHTML='<div><div class="name">'+name+'</div></div><div style="text-align:right"><div class="chip '+(keyed?'ok':'no')+'">'+(keyed?'key OK':'no key')+'</div><br><div class="chip '+cc+'">'+circ+'</div><br><div class="meta">elo '+(p.elo!=null?p.elo:'?')+' - '+(p.models||0)+' models</div></div>';
  prov.appendChild(el);
 }
 const m=await api('/v1/models');for(const a of (m.data||[]).map(x=>x.id)){const o=document.createElement('option');o.value=a;o.textContent=a;sel.appendChild(o);}
}
document.getElementById('send').onclick=async()=>{
 const out=document.getElementById('out');out.textContent='...';
 const body={model:document.getElementById('model').value,messages:[{role:'user',content:document.getElementById('prompt').value}]};
 const r=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json','X-Sovereign-Strategy':document.getElementById('strategy').value},body:JSON.stringify(body)});
 const t=await r.text();out.textContent=t.slice(0,4000);
 document.getElementById('routed').textContent='routed: '+(r.headers.get('X-Routed-Via')||'?')+' - '+(r.headers.get('X-Latency')||'?')+'s - '+(r.headers.get('X-Strategy')||'?');
};
document.getElementById('stream').onclick=async()=>{
 const out=document.getElementById('out');out.textContent='';
 const body={model:document.getElementById('model').value,stream:true,messages:[{role:'user',content:document.getElementById('prompt').value}]};
 const r=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json','X-Sovereign-Strategy':document.getElementById('strategy').value},body:JSON.stringify(body)});
 const rd=r.body.getReader();const dec=new TextDecoder();
 while(true){const d=await rd.read();if(d.done)break;out.textContent+=dec.decode(d.value);}
 document.getElementById('routed').textContent='routed: '+(r.headers.get('X-Routed-Via')||'?');
};
load();
</script></body></html>`;

type ChatBody = Record<string, unknown> & {
  model?: string;
  stream?: boolean;
  messages?: unknown[];
};

type RouteResult = {
  ok: boolean;
  status: number;
  provider?: string;
  model?: string;
  lat?: number;
  data?: Uint8Array | string;
  stream?: ReadableStream<Uint8Array> | null;
  err?: string;
  winner?: number;
};

// ---------------------------------------------------------------------------
// HealthDB (SQLite WAL) — same schema as Python
// ---------------------------------------------------------------------------
class HealthDB {
  conn: Database;

  constructor(path: string) {
    const dir = dirname(path);
    try {
      Bun.spawnSync(["mkdir", "-p", dir]);
    } catch {
      /* ok */
    }
    this.conn = new Database(path);
    this.conn.exec("PRAGMA journal_mode=WAL");
    this.conn.exec("PRAGMA synchronous=NORMAL");
    this.migrate();
  }

  migrate(): void {
    this.conn.exec(`
      CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        status INTEGER NOT NULL,
        latency_ms REAL NOT NULL,
        strategy TEXT NOT NULL DEFAULT '',
        winner INTEGER NOT NULL DEFAULT 0,
        session_id TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS idx_req_prov_model ON requests(provider, model);
      CREATE INDEX IF NOT EXISTS idx_req_ts ON requests(ts);

      CREATE TABLE IF NOT EXISTS model_health (
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        window_start REAL NOT NULL,
        successes INTEGER NOT NULL DEFAULT 0,
        failures INTEGER NOT NULL DEFAULT 0,
        rate_limited INTEGER NOT NULL DEFAULT 0,
        total_ms REAL NOT NULL DEFAULT 0,
        min_ms REAL NOT NULL DEFAULT 999999,
        max_ms REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (provider, model, window_start)
      );

      CREATE TABLE IF NOT EXISTS healing_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        event TEXT NOT NULL,
        prev_status TEXT NOT NULL DEFAULT '',
        new_status TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT ''
      );

      CREATE TABLE IF NOT EXISTS rate_limit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        status_code INTEGER NOT NULL,
        retry_after REAL DEFAULT NULL
      );

      CREATE TABLE IF NOT EXISTS session_affinity (
        session_id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        updated_at REAL NOT NULL
      );
    `);
  }

  recordRequest(
    provider: string,
    model: string,
    status: number,
    latencyMs: number,
    strategy = "",
    winner = 0,
    sessionId = "",
  ): void {
    const now = Date.now() / 1000;
    const window = now - (now % 300);
    this.conn
      .query(
        `INSERT INTO requests (ts,provider,model,status,latency_ms,strategy,winner,session_id)
         VALUES (?,?,?,?,?,?,?,?)`,
      )
      .run(
        now,
        provider,
        model,
        status,
        latencyMs,
        strategy,
        winner,
        sessionId,
      );

    if (status === 200) {
      this.conn
        .query(
          `INSERT INTO model_health
           (provider,model,window_start,successes,failures,total_ms,min_ms,max_ms)
           VALUES (?,?,?,1,0,?,?,?)
           ON CONFLICT(provider,model,window_start) DO UPDATE SET
             successes=successes+1, total_ms=total_ms+excluded.total_ms,
             min_ms=min(min_ms,excluded.min_ms), max_ms=max(max_ms,excluded.max_ms)`,
        )
        .run(provider, model, window, latencyMs, latencyMs, latencyMs);
    } else if (status === 429) {
      this.conn
        .query(
          `INSERT INTO model_health
           (provider,model,window_start,successes,failures,rate_limited,total_ms,min_ms,max_ms)
           VALUES (?,?,?,0,0,1,?,?,?)
           ON CONFLICT(provider,model,window_start) DO UPDATE SET
             rate_limited=rate_limited+1`,
        )
        .run(provider, model, window, latencyMs, latencyMs, latencyMs);
    } else {
      this.conn
        .query(
          `INSERT INTO model_health
           (provider,model,window_start,successes,failures,total_ms,min_ms,max_ms)
           VALUES (?,?,?,0,1,?,?,?)
           ON CONFLICT(provider,model,window_start) DO UPDATE SET
             failures=failures+1, total_ms=total_ms+excluded.total_ms,
             min_ms=min(min_ms,excluded.min_ms), max_ms=max(max_ms,excluded.max_ms)`,
        )
        .run(provider, model, window, latencyMs, latencyMs, latencyMs);
    }
  }

  recordRateLimit(provider: string, model: string, statusCode: number): void {
    this.conn
      .query(
        `INSERT INTO rate_limit_events (ts,provider,model,status_code,retry_after)
         VALUES (?,?,?,?,NULL)`,
      )
      .run(Date.now() / 1000, provider, model, statusCode);
  }

  recordHealing(
    provider: string,
    model: string,
    event: string,
    prevStatus = "",
    newStatus = "",
    details = "",
  ): void {
    this.conn
      .query(
        `INSERT INTO healing_events
         (ts,provider,model,event,prev_status,new_status,details)
         VALUES (?,?,?,?,?,?,?)`,
      )
      .run(
        Date.now() / 1000,
        provider,
        model,
        event,
        prevStatus,
        newStatus,
        details,
      );
  }

  getProviderSummary(): Record<
    string,
    {
      successes: number;
      failures: number;
      success_rate: number | null;
      avg_latency_ms: number | null;
      rate_limited: number;
    }
  > {
    const cutoff = Date.now() / 1000 - 1800;
    const rows = this.conn
      .query(
        `SELECT provider AS provider,
                SUM(successes) AS successes,
                SUM(failures) AS failures,
                AVG(total_ms / max(successes+failures,1)) AS avg_ms,
                SUM(rate_limited) AS rate_limited
         FROM model_health
         WHERE window_start>=? GROUP BY provider`,
      )
      .all(cutoff) as {
      provider: string;
      successes: number;
      failures: number;
      avg_ms: number | null;
      rate_limited: number;
    }[];
    const result: ReturnType<HealthDB["getProviderSummary"]> = {};
    for (const r of rows) {
      const s = r.successes || 0;
      const f = r.failures || 0;
      const total = s + f;
      result[r.provider] = {
        successes: s,
        failures: f,
        success_rate: total > 0 ? Math.round((s / total) * 1000) / 1000 : null,
        avg_latency_ms:
          r.avg_ms != null ? Math.round(Number(r.avg_ms) * 10) / 10 : null,
        rate_limited: r.rate_limited || 0,
      };
    }
    return result;
  }

  stickyGet(
    sessionId: string,
    ttl = STICKY_TTL,
  ): [string | null, string | null] {
    const cutoff = Date.now() / 1000 - ttl;
    const row = this.conn
      .query(
        `SELECT provider, model FROM session_affinity
         WHERE session_id=? AND updated_at>=?`,
      )
      .get(sessionId, cutoff) as { provider: string; model: string } | null;
    return row ? [row.provider, row.model] : [null, null];
  }

  stickySet(sessionId: string, provider: string, model: string): void {
    this.conn
      .query(
        `INSERT INTO session_affinity (session_id, provider, model, updated_at)
         VALUES (?,?,?,?)
         ON CONFLICT(session_id) DO UPDATE SET
           provider=excluded.provider, model=excluded.model, updated_at=excluded.updated_at`,
      )
      .run(sessionId, provider, model, Date.now() / 1000);
  }

  recentHealing(provider: string, limit = 10) {
    return this.conn
      .query(
        `SELECT ts,model,event,prev_status,new_status,details
         FROM healing_events WHERE provider=?
         ORDER BY ts DESC LIMIT ?`,
      )
      .all(provider, limit);
  }

  debugAgg() {
    return this.conn
      .query(
        `SELECT model, provider, status, count(*), avg(latency_ms)
         FROM requests GROUP BY model, provider, status
         ORDER BY count(*) DESC LIMIT 20`,
      )
      .all();
  }
}

// ---------------------------------------------------------------------------
// Matrix state
// ---------------------------------------------------------------------------
class Matrix {
  fail = new Map<string, [number, number]>();
  elo = new Map<string, number>();
  circuit = new Map<string, string>();
  circuitOpenUntil = new Map<string, number>();
  fifoDepth = 0;
  health: HealthDB;

  constructor() {
    for (const p of Object.keys(PROVIDERS)) {
      this.elo.set(p, 1000);
      this.circuit.set(p, "closed");
    }
    this.health = new HealthDB(DB_PATH);
  }

  record(
    model: string,
    prov: string,
    status: number,
    lat: number,
    winner = 0,
    strategy = "",
    session = "",
  ): void {
    const latMs = lat * 1000;
    this.health.recordRequest(
      prov,
      model,
      status,
      latMs,
      strategy,
      winner,
      session,
    );
    if (status === 200) {
      const old = this.circuit.get(prov) || "closed";
      this.elo.set(prov, (this.elo.get(prov) || 1000) + 16);
      this.fail.set(prov, [0, Date.now() / 1000]);
      this.circuit.set(prov, "closed");
      if (old !== "closed") {
        this.health.recordHealing(
          prov,
          model,
          "circuit_recovered",
          old,
          "closed",
        );
      }
    } else if (status === 429) {
      this.health.recordRateLimit(prov, model, status);
      this.elo.set(prov, Math.max(100, (this.elo.get(prov) || 1000) - 8));
      const [c] = this.fail.get(prov) || [0, 0];
      this.fail.set(prov, [c + 1, Date.now() / 1000]);
    } else {
      const [c] = this.fail.get(prov) || [0, 0];
      this.fail.set(prov, [c + 1, Date.now() / 1000]);
      this.elo.set(prov, Math.max(100, (this.elo.get(prov) || 1000) - 32));
      if (c + 1 >= 3) {
        const old = this.circuit.get(prov) || "closed";
        this.circuit.set(prov, "open");
        this.circuitOpenUntil.set(prov, Date.now() / 1000 + 60);
        this.health.recordHealing(
          prov,
          model,
          "circuit_opened",
          old,
          "open",
          `${c + 1} consecutive failures`,
        );
      }
    }
  }

  stickyGet(sid: string) {
    return this.health.stickyGet(sid, STICKY_TTL);
  }
  stickySet(sid: string, p: string, m: string) {
    this.health.stickySet(sid, p, m);
  }

  circuitOk(p: string): boolean {
    const st = this.circuit.get(p) || "closed";
    if (st === "closed") return true;
    if (st === "open") {
      if (Date.now() / 1000 > (this.circuitOpenUntil.get(p) || 0)) {
        this.circuit.set(p, "half");
        return true;
      }
      return false;
    }
    return true; // half-open probe
  }
}

const state = new Matrix();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getKey(p: string): string {
  const conf = PROVIDERS[p];
  if (!conf) return "";
  if (conf.no_auth) return "not-required-for-local";
  return (
    process.env[conf.key_env] ||
    (conf.key_env_alt ? process.env[conf.key_env_alt] : "") ||
    ""
  );
}
function keyOk(p: string): boolean {
  if (p === "llama-swap" || PROVIDERS[p]?.no_auth) return true;
  const conf = PROVIDERS[p];
  if (!conf) return false;
  return Boolean(
    process.env[conf.key_env] ||
    (conf.key_env_alt ? process.env[conf.key_env_alt] : ""),
  );
}
function firstModelFor(p: string): string {
  if (p === "llama-swap") return LOCAL_ROLES.quality;
  return PROVIDER_MODELS[p]?.[0] || "";
}

/** Local llama-swap catalog id heuristics (no cloud leak). */
function isLocalSwapModelId(model: string): boolean {
  if (!model || model === "auto" || model === "fcm") return false;
  if (model in CODING && CODING[model]?.[0] === "llama-swap") return true;
  if (
    model === LOCAL_ROLES.fast ||
    model === LOCAL_ROLES.quality ||
    model === LOCAL_ROLES.longctx
  ) {
    return true;
  }
  // sovereign naming prefixes / known local ids
  return /^(beellama|mradermacher|jackrong|turboquant|ik_llama|ik_turboquant|holo|qwen\/|gemma-4|exaone)/i.test(
    model,
  );
}

function resolveModel(model: string): [string, string] {
  if (model in CODING && CODING[model] != null) return CODING[model]!;
  // Prefer llama-swap for any local GGUF id so hybrid never sends GPU models to Gemini
  if (isLocalSwapModelId(model)) return ["llama-swap", model];
  if (model === "auto" || model === "fcm") {
    // local-first auto: quality role on swap
    return ["llama-swap", LOCAL_ROLES.quality];
  }
  for (const [p, models] of Object.entries(PROVIDER_MODELS)) {
    if (models.includes(model)) return [p, model];
  }
  if (keyOk("openrouter")) return ["openrouter", model];
  if (keyOk("nvidia")) return ["nvidia", model];
  return ["llama-swap", LOCAL_ROLES.quality];
}

function isAst(text: string): boolean {
  return Boolean(
    text && (AST_RE.test(text.slice(0, 5000)) || text.includes("```")),
  );
}

function isExplicit(model: string): boolean {
  return (
    (model in CODING && CODING[model] != null) || isLocalSwapModelId(model)
  );
}

function log(...args: unknown[]) {
  console.error("[matrix]", ...args);
}

// ---------------------------------------------------------------------------
// Provider call
// ---------------------------------------------------------------------------
async function callOne(
  provider: string,
  model: string,
  body: ChatBody,
  stream = false,
): Promise<RouteResult> {
  if (!state.circuitOk(provider)) {
    return {
      ok: false,
      status: 503,
      provider,
      lat: 0,
      err: "circuit_open",
    };
  }
  const conf = PROVIDERS[provider];
  if (!conf) {
    return {
      ok: false,
      status: 500,
      provider,
      lat: 0,
      err: "unknown_provider",
    };
  }
  const url = conf.base.replace(/\/$/, "") + "/chat/completions";
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": UA,
    "Accept-Encoding": "identity",
  };
  if (!conf.no_auth) {
    headers.Authorization = `Bearer ${getKey(provider)}`;
  } else {
    headers.Authorization = "Bearer not-required-for-local";
  }
  if (provider === "openrouter") {
    headers["HTTP-Referer"] = "https://zed.dev";
    headers["X-Title"] = "Sovereign-Router";
  }
  const payload = { ...body, model, stream };
  const start = performance.now();
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(stream ? 180_000 : 120_000),
    });
    const lat = (performance.now() - start) / 1000;
    if (!resp.ok) {
      const errText = (await resp.text()).slice(0, 500);
      state.record(model, provider, resp.status, lat, 0, STRATEGY);
      return {
        ok: false,
        status: resp.status,
        provider,
        lat,
        err: errText,
      };
    }
    if (stream) {
      state.record(model, provider, 200, lat, 0, STRATEGY);
      if (state.circuit.get(provider) === "half")
        state.circuit.set(provider, "closed");
      return {
        ok: true,
        status: resp.status,
        provider,
        model,
        lat,
        stream: resp.body,
      };
    }
    const data = await resp.arrayBuffer();
    state.record(model, provider, resp.status, lat, 0, STRATEGY);
    if (state.circuit.get(provider) === "half")
      state.circuit.set(provider, "closed");
    return {
      ok: true,
      status: resp.status,
      data: new Uint8Array(data),
      provider,
      model,
      lat,
    };
  } catch (e) {
    const lat = (performance.now() - start) / 1000;
    state.record(model, provider, 500, lat, 0, STRATEGY);
    return {
      ok: false,
      status: 500,
      provider,
      lat,
      err: String(e),
    };
  }
}

function pickWeighted(n = MAX_PARALLEL): [string, string][] {
  const scored: [number, string, string][] = [];
  for (const p of Object.keys(PROVIDERS)) {
    if (!keyOk(p) || !state.circuitOk(p)) continue;
    const sc = (state.elo.get(p) || 1000) + Math.random() * 10;
    const mid = firstModelFor(p);
    if (mid) scored.push([sc, p, mid]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  const out: [string, string][] = [];
  const seen = new Set<string>();
  for (const [, p, mid] of scored) {
    if (seen.has(p)) continue;
    seen.add(p);
    out.push([p, mid]);
    if (out.length >= n) break;
  }
  if (!out.length && keyOk("openrouter")) {
    out.push(["openrouter", "tencent/hy3:free"]);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------
async function routeAstRace(
  body: ChatBody,
  session: string,
  candsOverride?: [string, string][],
): Promise<RouteResult> {
  const model = String(body.model || "auto");
  if (isExplicit(model) && !candsOverride) {
    const [p, mid] = CODING[model]!;
    const r = await callOne(p, mid, body);
    if (r.ok) {
      state.stickySet(session, p, mid);
      state.record(mid, p, 200, r.lat || 0, 1, "ast_race");
    }
    return r;
  }
  const cands = candsOverride || pickWeighted(MAX_PARALLEL);
  if (!cands.length)
    return { ok: false, status: 503, err: "ast_race_exhausted" };
  const futs = cands.map(([p, mid]) => callOne(p, mid, body));
  let best: RouteResult | null = null;
  try {
    const results = await Promise.race([
      Promise.allSettled(futs).then((all) => all),
      new Promise<"timeout">((res) => setTimeout(() => res("timeout"), 95_000)),
    ]);
    if (results !== "timeout") {
      for (const settled of results) {
        if (settled.status !== "fulfilled" || !settled.value.ok) continue;
        const r = settled.value;
        let content = "";
        try {
          const j = JSON.parse(
            typeof r.data === "string"
              ? r.data
              : new TextDecoder().decode(r.data as Uint8Array),
          );
          content = j?.choices?.[0]?.message?.content || "";
        } catch {
          content = "";
        }
        if (isAst(content)) {
          state.stickySet(session, r.provider!, r.model!);
          state.record(r.model!, r.provider!, 200, r.lat || 0, 1, "ast_race");
          return r;
        }
        if (!best) best = r;
      }
    } else {
      // timeout: take first completed ok if any
      for (const f of futs) {
        const settled = await Promise.race([
          f.then((v) => v),
          Promise.resolve(null as RouteResult | null),
        ]);
        if (settled?.ok) {
          best = settled;
          break;
        }
      }
    }
  } catch {
    /* exhausted */
  }
  if (best?.ok) {
    state.stickySet(session, best.provider!, best.model!);
    return best;
  }
  return { ok: false, status: 503, err: "ast_race_exhausted" };
}

async function routeSticky(
  body: ChatBody,
  session: string,
): Promise<RouteResult> {
  const model = String(body.model || "auto");
  if (isExplicit(model)) return routeAstRace(body, session);
  const [p, m] = state.stickyGet(session);
  if (p && keyOk(p) && state.circuitOk(p)) {
    const r = await callOne(p, m || model, body);
    if (r.ok) return r;
  }
  return routeAstRace(body, session);
}

async function routeWeighted(
  body: ChatBody,
  session: string,
): Promise<RouteResult> {
  const cands = pickWeighted(1);
  if (!cands.length) return { ok: false, status: 503, err: "no_providers" };
  const [p, mid] = cands[0];
  const r = await callOne(p, mid, body);
  if (r.ok) state.stickySet(session, p, mid);
  return r;
}

async function routeCircuitChain(
  body: ChatBody,
  session: string,
): Promise<RouteResult> {
  const model = String(body.model || "auto");
  if (isExplicit(model)) {
    const [p, mid] = CODING[model]!;
    if (keyOk(p) && state.circuitOk(p)) {
      const r = await callOne(p, mid, body);
      if (r.ok) {
        state.stickySet(session, p, mid);
        return r;
      }
    }
    return {
      ok: false,
      status: 502,
      err: `explicit_provider_unavailable:${p}`,
    };
  }
  const order = Object.keys(PROVIDERS).sort(
    (a, b) => (state.elo.get(b) || 1000) - (state.elo.get(a) || 1000),
  );
  for (const p of order) {
    if (!keyOk(p) || !state.circuitOk(p)) continue;
    const mid = firstModelFor(p);
    if (!mid) continue;
    const r = await callOne(p, mid, body);
    if (r.ok) {
      state.stickySet(session, p, mid);
      return r;
    }
  }
  return { ok: false, status: 503, err: "circuit_chain_exhausted" };
}

async function routeFifo(
  body: ChatBody,
  session: string,
): Promise<RouteResult> {
  if (state.fifoDepth >= FIFO_MAX) {
    return { ok: false, status: 429, err: "fifo_full" };
  }
  state.fifoDepth++;
  try {
    return await routeAstRace(body, session);
  } finally {
    state.fifoDepth = Math.max(0, state.fifoDepth - 1);
  }
}

async function routeHybrid(
  body: ChatBody,
  session: string,
): Promise<RouteResult> {
  const model = String(body.model || "auto");
  if (isExplicit(model)) {
    const [p, mid] = resolveModel(model);
    const r = await callOne(p, mid, body);
    if (r.ok) {
      state.stickySet(session, p, mid);
      state.record(mid, p, 200, r.lat || 0, 1, "hybrid_direct");
    }
    return r;
  }
  const [p, m] = state.stickyGet(session);
  if (p && keyOk(p) && state.circuitOk(p)) {
    const r = await callOne(p, m || model, body);
    if (r.ok) return r;
  }
  const r2 = await routeAstRace(body, session);
  if (r2.ok) return r2;
  return routeCircuitChain(body, session);
}

const ROUTERS: Record<
  string,
  (body: ChatBody, session: string) => Promise<RouteResult>
> = {
  fifo_matrix: routeFifo,
  ast_race: routeAstRace,
  sticky_affinity: routeSticky,
  weighted_elo: routeWeighted,
  circuit_chain: routeCircuitChain,
  hybrid: routeHybrid,
  free: routeFree,
};

// freeCandidates: every ":free" model across keyed providers, plus the local
// llama-swap (always zero-cost). This is the pool the `free` strategy races.
function freeCandidates(): [string, string][] {
  const out: [string, string][] = [];
  for (const [name, conf] of Object.entries(PROVIDERS)) {
    if (!keyOk(name) || !state.circuitOk(name)) continue;
    for (const mid of PROVIDER_MODELS[name] || []) {
      if (mid.includes(":free")) out.push([name, mid]);
    }
  }
  if (keyOk("llama-swap")) {
    out.push(["llama-swap", LOCAL_ROLES.fast]);
    out.push(["llama-swap", LOCAL_ROLES.quality]);
    out.push(["llama-swap", LOCAL_ROLES.longctx]);
  }
  return out;
}

// routeFree: maximal free-provider strategy. Races the free+local candidate
// pool through the SAME parallel-race / AST-preference / sticky / circuit
// machinery as ast_race — so local GPU and free cloud models compete on equal
// footing, and circuit breakers still apply per provider.
async function routeFree(
  body: ChatBody,
  session: string,
): Promise<RouteResult> {
  const cands = freeCandidates();
  if (!cands.length)
    return { ok: false, status: 503, err: "no_free_providers" };
  return routeAstRace(body, session, cands);
}

// ---------------------------------------------------------------------------
// HTTP

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------
function sessionId(req: Request, body: ChatBody): string {
  const h = req.headers.get("X-Session-Id");
  if (h) return h;
  const seed = JSON.stringify((body.messages || []).slice(0, 1));
  return createHash("md5").update(seed).digest("hex").slice(0, 12);
}

function json(
  data: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

async function handleStream(
  body: ChatBody,
  sid: string,
  _strat: string,
): Promise<Response> {
  const model = String(body.model || "auto");
  const tryStream = async (p: string, mid: string) => {
    const r = await callOne(p, mid, body, true);
    if (!r.ok || !r.stream) return null;
    state.stickySet(sid, p, mid);
    return new Response(r.stream, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Routed-Via": `${p}/${mid}`,
      },
    });
  };

  if (isExplicit(model)) {
    const [p, mid] = CODING[model]!;
    const resp = await tryStream(p, mid);
    if (resp) return resp;
  } else {
    const [sp, sm] = state.stickyGet(sid);
    if (sp && keyOk(sp) && state.circuitOk(sp)) {
      const resp = await tryStream(sp, sm || model);
      if (resp) return resp;
    }
  }

  const cands = isExplicit(model)
    ? [CODING[model]!]
    : pickWeighted(MAX_PARALLEL);
  for (const [p, mid] of cands) {
    const resp = await tryStream(p, mid);
    if (resp) return resp;
  }
  return json({ error: "all_stream_providers_exhausted" }, 503);
}

const server = Bun.serve({
  port: PORT,
  hostname: "127.0.0.1",
  async fetch(req) {
    const url = new URL(req.url);
    const path = url.pathname;

    if (path.startsWith("/mesh")) {
      const m = await handleMeshRequest(req, {
        service: "sovereign-router",
        version: "v3.1",
      });
      if (m) return m;
    }

    if (req.method === "GET" && (path === "/v1/models" || path === "/models")) {
      const data = Object.keys(CODING).map((id) => ({ id, object: "model" }));
      return json({ object: "list", data });
    }

    if (req.method === "GET" && (path === "/ui" || path === "/ui/")) {
      return new Response(ROUTER_UI_HTML, {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }
    if (req.method === "GET" && path === "/ui/data") {
      return json(uiData());
    }

    if (req.method === "GET" && path === "/health") {
      const dbSummary = state.health.getProviderSummary();
      const providers: Record<string, unknown> = {};
      for (const p of Object.keys(PROVIDERS)) {
        providers[p] = {
          keys: keyOk(p) ? "configured" : "no_key",
          elo: Math.round((state.elo.get(p) || 1000) * 10) / 10,
          circuit: state.circuit.get(p) || "unknown",
          models: (PROVIDER_MODELS[p] || []).length,
          health: dbSummary[p] || null,
        };
      }
      return json({
        status: "ok",
        router: "sovereign-router-ts",
        version: "v3.1",
        strategy: STRATEGY,
        parallel: MAX_PARALLEL,
        providers,
      });
    }

    if (req.method === "GET" && path === "/debug/sqlite") {
      try {
        return json(state.health.debugAgg());
      } catch (e) {
        return json({ error: String(e) }, 500);
      }
    }

    if (req.method === "GET" && path === "/debug/health") {
      try {
        const healing: Record<string, unknown> = {};
        for (const p of Object.keys(PROVIDERS)) {
          healing[p] = state.health.recentHealing(p);
        }
        return json({
          summary: state.health.getProviderSummary(),
          healing,
        });
      } catch (e) {
        return json({ error: String(e) }, 500);
      }
    }

    if (req.method === "POST" && path.includes("/chat/completions")) {
      let body: ChatBody;
      try {
        body = (await req.json()) as ChatBody;
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      const sid = sessionId(req, body);
      const strat = req.headers.get("X-Sovereign-Strategy") || STRATEGY;
      log(`${req.method} ${path} model=${body.model} strat=${strat}`);

      if (body.stream) {
        return handleStream(body, sid, strat);
      }

      const fn = ROUTERS[strat] || routeHybrid;
      const r = await fn(body, sid);
      if (r.ok) {
        return new Response(r.data as BodyInit, {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "X-Routed-Via": `${r.provider}/${r.model}`,
            "X-Latency": String(Math.round((r.lat || 0) * 1000) / 1000),
            "X-Strategy": strat,
          },
        });
      }
      return json(
        { error: r.err || "exhausted", status: r.status },
        r.status || 503,
      );
    }

    return new Response("Not Found", { status: 404 });
  },
});

const keyed = Object.keys(PROVIDERS).filter(keyOk);
console.log(`Sovereign Router TS v3.1 on http://127.0.0.1:${PORT}/v1`);
console.log(
  `Strategy=${STRATEGY} | routes: ${Object.keys(ROUTERS).join(", ")}`,
);
console.log(`Streaming=SSE | Providers: ${keyed.join(", ") || "(none)"}`);
console.log(`Health DB: ${DB_PATH} (WAL)`);
console.log(`Listening ${server.hostname}:${server.port}`);

// hotreload-probe 1784356795195
