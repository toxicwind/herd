# llama-swap (sovereign runtime)

This directory is the **runtime home** for the inference front door — not a second source tree.

| Path                 | Role                                                                                    |
| -------------------- | --------------------------------------------------------------------------------------- |
| `llama-swap`         | Symlink → `/home/toxic/projects/llama-swap-main/llama-swap` (**toxicwind fork** binary) |
| `config.yaml`        | Live config (RTX 3090 / sm_86, routing matrix, macros for 4 llama.cpp forks)            |
| `MODEL_INVENTORY.md` | Local GGUF / model-id audit for this host                                               |
| `ollama-proxy`       | Optional sibling symlink (legacy)                                                       |

## Source of truth for code

|               |                                                            |
| ------------- | ---------------------------------------------------------- |
| **Fork repo** | https://github.com/toxicwind/llama-swap                    |
| **Upstream**  | https://github.com/mostlygeek/llama-swap                   |
| **Checkout**  | `/home/toxic/projects/llama-swap-main`                     |
| **Fork docs** | Read **“Fork additions”** in that repo’s `README.md` first |

Do **not** treat this README as upstream documentation. Upstream feature list + install lives in the fork checkout README (with our additions called out at the top).

## Why a fork

Sovereign clients (Zed llama.cpp provider, OpenFang `provider = "llama"`, Grok, IDE oaicopilot) need:

1. Stable **OpenAI-compatible streaming** even when backends differ → `normalize_sse`
2. **Model discovery events** for Zed → `GET /models/sse`
3. Reliable restarts when orphan `llama-server` holds ports → pre-spawn `fuser -k`
4. **IPv4 loopback** defaults (`127.0.0.1`) so dual-stack `localhost` does not break dial

## Ports (SSOT: `config/ports.env`)

| Env                                 | Port        | Surface                     |
| ----------------------------------- | ----------- | --------------------------- |
| `LLAMA_SWAP_PORT`                   | **25100**   | Proxy + `/ui` + `/v1`       |
| `LLAMA_START_PORT`–`LLAMA_END_PORT` | 25001–25099 | Backend slots owned by swap |

Health: `curl -sS http://127.0.0.1:25100/health` → `OK`

## Operate

```text
# via sovereign stack
cd /home/toxic/sovereign && mise run up     # includes llama-swap module
mise run restart-llama
mise run health

# binary only
/home/toxic/sovereign/tools/llama-swap/llama-swap \
  -config /home/toxic/sovereign/tools/llama-swap/config.yaml \
  -listen 127.0.0.1:25100
```

## Rebuild fork binary

```text
cd /home/toxic/projects/llama-swap-main
go build -o llama-swap .
# symlink already points here
```

## Related

- Stack rules: `/home/toxic/sovereign/AGENTS.md` (via `~/.grok/AGENTS.md`) — **no vLLM**
- Ops dashboard (rust-web): `http://127.0.0.1:25101/` — APIs under `/ops/api/*`
