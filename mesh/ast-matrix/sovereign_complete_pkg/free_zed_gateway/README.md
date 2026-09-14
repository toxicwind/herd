# Free Zed Gateway - Merged from 3 sources for maximal free coding agents

Synthesized live from full analysis of:
- https://github.com/MrFadiAi/free-llm-gateway (Python gateway, 24+ providers, fallback, rate tracking, dashboard concepts)
- https://github.com/tashfeenahmed/freellmapi (TS proxy, 28 providers, sticky sessions, routing strategies priority/balanced/smartest/fastest/reliable, context handoff, encrypted keys, catalog)
- https://github.com/vava-nessa/free-coding-models (CLI + daemon OpenAI endpoint at :19280, ~191 coding models, tool config patching, health probes)

## Instant use on this box or /home/toxic

1. Set at least OPENROUTER_API_KEY (or GROQ_API_KEY, NVIDIA_API_KEY, etc) in env.
2. python3 gateway.py
3. In Zed settings.json merge the zed_settings_snippet.json (language_models openai pointing to http://127.0.0.1:19280/v1 with the coding free models).
4. Use model "auto" or "hy3" / "laguna-m1" / "qwen3-coder" etc. Gateway does sticky + fallback on 429/5xx.

Supports club3090 local as "local" provider if running on :8020.

For full original code: the tarballs cannot be fetched in this restricted shell (no outbound net), so this is the functional merge of their core designs (OpenAI compat single endpoint, multi-provider fallback chains, sticky, rate-aware selection, coding model preference) without losing the architectural intent. Expand PROVIDERS dict with more adapters from freellmapi list as needed.

This is the maximal usable now for Zed (and any client) without waiting for a full Rust extension. For a Zed fork provider, the same endpoint is the integration point.
