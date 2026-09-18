# herd

> **herd** — run a whole herd of LLM backends behind one OpenAI-compatible API.

herd is a fork of [mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap) (upstream), extended with
herd-specific infrastructure: AST Matrix V2 smart routing, an agentic lens suite, and hardening fixes for
real-world deployments. The fork keeps upstream's core (swap models in and out of VRAM on demand,
OpenAI-compatible endpoints) and layers herd's production tooling on top.

**Runs native — no container required.** The machine is the platform: we operate herd under
mise + pitchfork, and plain `go build` works anywhere. Docker images exist only as a fallback
for folks who can't or won't run the native stack — see
[🐳 Docker (fallback — not recommended)](#-docker-fallback--not-recommended).

## Quickstart

```bash
git clone https://github.com/toxicwind/herd.git
cd herd
make clean all        # or: go build -o herd .
```

Create a config (see upstream docs for the full schema) and run:

```bash
./herd --config config.yaml --listen 127.0.0.1:8080
```

## Why a fork

Sovereign clients need things upstream doesn't provide:

1. Stable **OpenAI-compatible streaming** even when backends differ → `normalize_sse`
2. **Model discovery events** for Zed → `GET /models/sse` (`internal/server/models_sse.go`)
3. Reliable restarts when an orphan `llama-server` holds a port → pre-spawn `fuser -k` (`internal/process/process_command.go`)
4. **IPv4 loopback** defaults (`127.0.0.1`) so dual-stack `localhost` does not break dial (`internal/config/model_config.go`)

## What's different from upstream

| Area | herd |
|---|---|
| Docker images | Fallback only (not recommended): `ghcr.io/toxicwind/herd:unified-<backend>` — see below |
| Routing | AST Matrix V2: token-bucket rate limiting + 5-strike circuit breaker (30s cooldown), 8 routing strategies |
| Providers | 13 built-in providers with base URLs (`internal/astmatrix/providers.go`) |
| SSE | `GET /models/sse` synthesized for Zed; SSE normalization via `normalize_sse` |
| Networking | IPv4 loopback default `127.0.0.1` (avoids localhost→::1 breakage) |
| Process mgmt | Frees stale ports with `fuser -k` before spawning backends |
| Sovereign | Built-in sovereign provider at `http://127.0.0.1:25100/v1` |
| Lenses | Agentic lens suite (stylometric authorship, OSINT infra recon, crypto leak detection) |
| Bench | Bench orchestrator in `internal/bench/orchestrator.go` |

### AST Matrix V2

Smart routing layer in `internal/astmatrix/` (stdlib-only, zero external dependencies). Full details in
[README_ASTMATRIX_V2.md](README_ASTMATRIX_V2.md).

- **Rate limiting:** token bucket (`ratelimit.go`)
- **Circuit breaker:** 5-strike, 30s cooldown (`circuit.go`)
- **Strategies (8):** `hybrid`, `ast_race`, `sticky_affinity`, `weighted_elo`, `least_latency`, `round_robin`, `free`, `circuit_chain`
- **Endpoints:** `/astmatrix/status`, `/astmatrix/metrics`

```yaml
astMatrix:
  astStrategy: hybrid
  requestTimeout: 30s
  maxRetries: 3
  healthProbeInterval: 10s
  enableCoalescing: true
```

## Ports

| Env | Port | Surface |
|---|---|---|
| `LLAMA_SWAP_PORT` | **25100** | Proxy + `/ui` + `/v1` |
| `LLAMA_START_PORT`–`LLAMA_END_PORT` | 25001–25099 | Backend slots owned by swap |

Health: `curl -sS http://127.0.0.1:25100/health` → `OK`

## Agentic lens suite

`src/_11ty/lenses/*.js` + `lib/lens-orchestrator.js`, run by `.github/workflows/tectonic-drift.yml`:

- Stylometric authorship analysis
- OSINT infrastructure reconnaissance
- Cryptographic leak detection
- Tectonic drift lenses

Configure via `.env.example`.

## Bench orchestrator

`internal/bench/orchestrator.go` — benchmark orchestration for backends/strategies.

## 🐳 Docker (fallback — not recommended)

[![Unified Docker](https://github.com/toxicwind/herd/actions/workflows/unified-docker.yml/badge.svg)](https://github.com/toxicwind/herd/actions/workflows/unified-docker.yml)

> ⚠️ **The sovereign take on Docker** 🐳🚫
>
> Docker works. It is also wrong for this stack, and we would rather tell you why than
> pretend otherwise:
>
> - **It fights your GPU.** Every container needs `--gpus`, `--runtime=nvidia`, device flags —
>   ceremony the native binary skips entirely. The GPU is *right there*. Talk to it directly.
> - **It turns 100GB of weights into a mount puzzle.** Your models live on disk. Docker makes you
>   re-expose them through volume mounts and then acts surprised when paths break.
> - **It is a second platform under your platform.** We run on mise + pitchfork: the machine is the
>   platform. Docker inserts a shadow init system, an image registry, and a build pipeline for zero
>   local benefit.
> - **It is slower to iterate.** Rebuild the image, push, pull, restart — versus `go build` and run.
>
> So why does it exist here at all? As an **export format**: for people who cannot or will not run
> the native stack, and as CI's clean-room proof that herd assembles from nothing. If the machine is
> yours, go native. You will be happier.

herd publishes its own images (not upstream's):

```
ghcr.io/toxicwind/herd:unified-<backend>
```

Built by `docker/unified/build-image.sh`, published by `.github/workflows/unified-docker.yml`.

> **Rootless build note (2026-09-14):** the rootless build stage must use plain `docker build`
> (docker driver), **not** the buildx container driver — otherwise
> `FROM ghcr.io/toxicwind/herd:unified-<backend>` fails to resolve the local tag. Nightly unified
> builds were failing for a week before this was fixed.

## Remotes

```bash
git remote -v
# origin    https://github.com/toxicwind/herd.git (fetch)
# origin    https://github.com/toxicwind/herd.git (push)
# upstream  https://github.com/mostlygeek/llama-swap.git (fetch)
```

herd tracks upstream `mostlygeek/llama-swap`; fork-specific work lives on `main` here.
