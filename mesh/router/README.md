# Sovereign Router

Multi-provider LLM **routing gateway** (OpenAI-compatible `/v1/chat/completions`).
It fans a single request across many upstream providers with strategy-based
failover, circuit breakers, sticky sessions, and a WAL health DB.

> Naming note: this was historically called "ast-matrix" / "ast-router" (a
> codename from the original research angle). It is a **provider router**, not a
> matrix — the directory is now `tools/sovereign-router`.

## What it actually is

A single HTTP server that, given a model alias (e.g. `free`, `hy3`,
`quality`, `nim-inkling`), picks the best upstream and returns the response.
Strategies decide *how* candidates are selected:

| Strategy | Behavior |
|----------|-----------|
| `hybrid` (default) | sticky → ast_race → circuit_chain |
| `free` | **races local llama-swap + every `:free` cloud model** (zero-cost) |
| `ast_race` | parallel N providers, first AST/code-shaped response wins |
| `sticky_affinity` | 30-min session pinning for multi-turn |
| `weighted_elo` | dynamic Elo from success/latency |
| `circuit_chain` | sequential with open/half-open circuit breakers |
| `fifo_matrix` | bounded FIFO queue (back-pressure) |

Set strategy per-request: `X-Sovereign-Strategy: free`.

## Layout (this directory)

```
tools/sovereign-router/
├── sovereign-router-ts/   # ← THE LIVE ROUTER (run by pitchfork :25104)
│   └── router.ts          # Bun/TS, self-contained + /ui dashboard
├── sovereign-ast-matrix-py/  # v2 Python router (reference / source-of-truth)
├── sovereign-ast-router/    # v3 TS variant (reference)
├── free_zed_gateway/       # free-LLM-gateway concept (folded into `free` strategy)
├── ultimate_extract/       # agent-infra research dump (NOT router code)
├── README_COMPLETE.txt      # original research notes
└── *.py / *.json           # provider-discovery catalogs (research inputs)
```

The **canonical/primary** implementation is the Go port inside llama-swap:
`~/projects/llama-swap-main/internal/astmatrix/` (mirrors this router; the
`free` strategy + `/ui` page were added there too).

## Free providers (maximal integration)

The `free` strategy is the zero-cost path. It builds a candidate pool of:

- **local llama-swap** (always free — `local-fast` / `local-quality` / `local-longctx`)
- **every `:free` model** across keyed cloud providers (OpenRouter's
  `tencent/hy3:free`, `poolside/laguna-*`, `qwen3-coder:free`,
  `gemma-4-31b-it:free`, `nemotron-*`, `hermes-3-*`, `gpt-oss-20b:free`, …)

and races them through the *same* parallel/AST-preference/circuit machinery
as `ast_race`. So local GPU and free cloud models compete on equal footing,
and circuit breakers still apply per provider.

## Run

```bash
# via mise/pitchfork (binds :25104)
mise run up            # starts sovereign-router (daemon: sovereign-router)

# or directly
cd tools/sovereign-router/sovereign-router-ts
SOVEREIGN_ROUTER_PORT=25104 bun run router.ts
```

## Endpoints

| Path | Method | Purpose |
|------|--------|---------|
| `/v1/chat/completions` | POST | route a chat completion |
| `/v1/models` | GET | list model aliases |
| `/health` | GET | provider/circuit/elo summary |
| `/ui` | GET | **self-contained dashboard** (providers, free models, live chat) |
| `/ui/data` | GET | JSON snapshot for external dashboards |
| `/debug/health` `/debug/sqlite` | GET | healing + raw health-DB aggregates |
| `/mesh/*` | GET | GHAS-inspired mesh feature registry |

## Dashboard

Open `http://127.0.0.1:25104/ui` (or the tailnet URL) to see the
provider matrix, which models are free-tier, live circuit/Elo state, and a
chat box that posts to `/v1/chat/completions` with a chosen strategy.
