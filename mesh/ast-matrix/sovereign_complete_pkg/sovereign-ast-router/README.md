# Sovereign AST Router

New project name merging:
- Previous free_zed_gateway
- 9Router concepts (from ULTIMATE_JULY_2026: RTK-style token awareness, 3-tier thinking, multi-provider, format ideas)
- free-llm-gateway + freellmapi + free-coding-models architectures
- ULTIMATE modular helpers (llm_client, curlx fallbacks, orchestrator, env_dump, switchover robustness patterns)

## Instant use
1. export OPENROUTER_API_KEY=... (and any of GROQ_API_KEY NVIDIA_API_KEY CEREBRAS_API_KEY GOOGLE_API_KEY MISTRAL_API_KEY)
2. python3 router.py
3. Merge zed_settings.json into your Zed (or Zed fork) settings.json
4. Use model "auto" — it races up to 4 free providers in parallel; first response that looks like AST/code wins. Sticky keeps multi-turn coherent. FIFO bounds concurrency.

Local club3090 on :8020 is automatically eligible as "local".

## Aggressive router design
- Parallel race of 4
- Winner = first with AST/code signals (def/class/import/function/const/fn/struct/``` etc.)
- FIFO matrix for back-pressure
- Failure cooldown + sticky 30 min
- Coding-first free models from live July 2026 ranking

## Modular integration
The extracted modules under ultimate_extract/ (llm_client, curlx patterns, orchestrator, env_dump, switchover, recon, etc.) can be imported or adapted for richer fallbacks, health, and k8s/s6 awareness. Copy them next to router.py as needed.

## Download / location
All files live at:
- /home/workdir/artifacts/sovereign-ast-router/
- /mnt/sovereign-ast-router/

No external download links possible from this restricted shell; these paths are the deliverable.
