# Sovereign Mesh — Tool Federation Gateway & AST Matrix

<<<<<<< HEAD
**Port**: `:25127` (MCP Proxy Gateway) | `:25115` (Mesh Hub)  
**Role**: Federated tool routing, AST matrix code navigation, and MCP client aggregation.
=======
**Ports**: `:25127` (MCP Proxy Gateway) | `:25115` (Mesh Hub) | `:25100` (Router/llama-swap) | `:25104` (Sovereign Router TS)  
**Role**: Federated tool routing, AST matrix code navigation, MCP client aggregation, and multi-provider LLM routing.
>>>>>>> origin/main

---

## 🏛️ Topology

<<<<<<< HEAD
Mesh unifies the tool gateway, dynamic AST Matrix routers, and proxy daemons under a single workspace:

```
mesh/
├── gateway/      ← MCP Proxy Go gateway (mcpproxy-go) connecting 43+ upstream servers
├── router/       ← Sovereign router TS & Python routing services
├── ast-matrix/   ← AST Matrix code extraction and semantic matrix packages
└── config.yml    ← Unified mesh configuration & port mappings
=======
```
mesh/
├── gateway/          ← MCPProxy Go gateway (mcpproxy-go) connecting 43+ upstream servers
│                       Port: :25127 | MCP client aggregation
├── router/           ← Sovereign Router — multi-provider LLM routing gateway
│   ├── sovereign-router-ts/      # LIVE ROUTER (Bun/TS, port :25104)
│   ├── sovereign-ast-matrix-py/  # v2 Python router (FastAPI)
│   ├── sovereign-ast-router/     # v3 TS variant
│   ├── sovereign-mcp-gateway/    # MCP gateway service
│   ├── free_zed_gateway/         # free-LLM-gateway concept
│   └── bin/                      # compiled binaries
├── ast-matrix/       ← AST Matrix code extraction and semantic matrix packages
├── ui-svelte/        ← Svelte dashboard for router/llama-swap UI
├── config.yml        ← Unified mesh configuration, model roles, and port mappings
├── research/         ← Research artifacts (provider discovery scripts, agent-infra dumps)
└── data/             ← JSON data dumps (model catalogs, package tables, scaffolds)
>>>>>>> origin/main
```

---

<<<<<<< HEAD
## 🚀 Quick Verification

```bash
# Verify mesh-hub is responding
curl -sf http://127.0.0.1:25115/health

# Verify mesh MCP gateway
curl -sf http://127.0.0.1:25127/health
=======
## 🔌 Ports & Services

| Port | Service | Description |
|------|---------|-------------|
| `:25127` | MCPProxy (Go) | MCP client aggregation gateway, 43+ upstream servers |
| `:25115` | Mesh Hub | Mesh service discovery and health |
| `:25100` | llama-swap | Local model inference (herd.yaml config) |
| `:25104` | Sovereign Router TS | Multi-provider LLM routing (Bun/TS + `/ui` dashboard) |
| `:25103` | OpenFang | External LLM service proxy |
| `:25105` | Prometheus | Metrics scraping |
| `:25106` | hf-downloader | HuggingFace model downloader |
| `:25110` | Grafana | Dashboard |
| `:25114` | next-server | sovereign-github-search frontend |

---

## 🎯 Model Roles

Mesh configures model routing via `config.yml`:

| Role | Model | Purpose |
|------|-------|---------|
| `default` | `openrouter/inclusionai/ling-3.0-flash-fin:free:high` | Default routing model |
| `task` | `qwen/qwen3.6-35b-a3b:high` | Task-oriented routing |
| `slow` | `qwen/qwen3.6-35b-a3b:high` | Slow/fallback routing |
| `plan` | `qwen/qwen3.6-35b-a3b:high` | Planning mode |
| `smol` | `qwen/qwen3.6-27b:high` | Small/smol routing |
| `tiny` | `qwen/qwen3.6-27b:high` | Tiny model routing |

The `free` strategy races local llama-swap + every `:free` cloud model.

---

## 📦 Router Strategies

Set strategy per-request: `X-Sovereign-Strategy: free`

| Strategy | Behavior |
|----------|----------|
| `hybrid` (default) | sticky → ast_race → circuit_chain |
| `free` | Races local llama-swap + every `:free` cloud model (zero-cost) |
| `ast_race` | Parallel N providers, first AST/code-shaped response wins |
| `sticky_affinity` | 30-min session pinning for multi-turn |
| `weighted_elo` | Dynamic Elo from success/latency |
| `circuit_chain` | Sequential with open/half-open circuit breakers |
| `fifo_matrix` | Bounded FIFO queue (back-pressure) |

---

## 🔗 Relationship to Herd

Herd owns the local inference layer (`llama-swap`, port `:25100`). Mesh owns the routing and gateway layer. Config connects them:

```yaml
openai-compatible:
    baseUrl: http://127.0.0.1:25100/v1
    apiKey: llama-swap
```

The `ui-svelte/` dashboard is served by the router's built-in `/ui` page.

---

## 🚀 Quick Verification

```bash
curl -sf http://127.0.0.1:25115/health    # mesh-hub
curl -sf http://127.0.0.1:25127/health    # MCP gateway
curl -sf http://127.0.0.1:25104/health    # sovereign router
curl -sf http://127.0.0.1:25100/v1/models  # llama-swap
>>>>>>> origin/main
```
