# Sovereign Router v2

Maximal free coding LLM gateway for Zed / Zed-fork.

## Routing strategies (5 + hybrid)

Research sources: RouteLLM (Elo), radlab llm-router (weighted/first_available), agent-router (sticky + circuit), PORT (weighted splits), LLM-Runner-Router (ensemble/self-healing), circuit-breaker patterns on GitHub 2025-2026.

1. **fifo_matrix** — bounded FIFO queue (back-pressure)
2. **ast_race** — parallel 4 providers; first AST/code-shaped response wins
3. **sticky_affinity** — 30 min session sticky for multi-turn
4. **weighted_elo** — dynamic Elo from success/latency
5. **circuit_chain** — sequential with open/half-open circuit breakers
6. **hybrid** (default) — sticky → ast_race of top-weighted → circuit_chain

Header override: `X-Sovereign-Strategy: ast_race` (etc.)

## Instant use
```bash
export OPENROUTER_API_KEY=sk-or-...
# optional: GROQ_API_KEY NVIDIA_API_KEY CEREBRAS_API_KEY GOOGLE_API_KEY MISTRAL_API_KEY
python3 router.py
# merge zed_settings.json into Zed settings.json
```

Local club3090 (or any OpenAI-compatible) on :8020 is auto-eligible.

## Modules
`lib/` holds flattened ULTIMATE helpers (llm_client, orchestrator, env_dump, switchover). Import or adapt for deeper health/recovery.

## Download paths (this environment)
- `/mnt/sovereign-router/`
- `/home/workdir/artifacts/sovereign-router/`
- Previous: `/mnt/sovereign-ast-router/` and `/mnt/free_zed_gateway/`
- Full module extract: `/home/workdir/artifacts/ultimate_extract/`

## NVIDIA NIM (complete)

Base URL used: `https://integrate.api.nvidia.com/v1`

1. Get a free API key at https://build.nvidia.com (key starts with `nvapi-`)
2. Export it:
   ```bash
   export NVIDIA_API_KEY=nvapi-...
   # or NVIDIA_NIM_API_KEY
   ```
3. Restart the router. Models prefixed `nim-` go directly to NVIDIA NIM.
4. In Zed pick any of the `nim-*` models from the openai provider list.

Direct NIM models now registered:
- nim-nemotron-super / nim-nemotron-nano
- nim-llama-3.3-70b / nim-llama-3.1-405b / nim-llama-3.1-70b
- nim-qwen3-coder / nim-qwen2.5-coder-32b
- nim-deepseek-r1 / nim-deepseek-v3
- nim-mistral-large / nim-phi-4 / nim-gemma-3-27b / nim-glm
