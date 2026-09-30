# Merging upstream llama-swap

This repo (`toxicwind/herd`) is a fork of [mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap).
We keep an `upstream` remote so we can merge their changes without losing our patches.

## The rule

**Upstream files keep upstream names.** `llama-swap.go` stays `llama-swap.go`.
`go.mod` keeps `module github.com/mostlygeek/llama-swap`. Renaming either one
turns every future upstream merge into a conflict. The herd identity lives in
the repo name, README, config, and UI — not in filenames upstream touches.

Our extensions live in clearly-named locations that upstream will never touch:
`internal/astmatrix/`, `internal/bench/`, `internal/freeproxy/`,
`internal/shared/`, `mesh/`, `cmd/herd-launcher/`, `cmd/herd-plane/`.

## How to merge

```bash
git fetch upstream
git merge upstream/main
# resolve conflicts — ours win on the 125 patched files (see below)
go build ./...
go test ./...
```

## Our patch surface (125 files, 2026-09-30)

These files exist upstream but we have modified. On merge conflicts, keep our
version unless the upstream change is a bugfix we want:

- `internal/config/` — config extensions (tailcat, macros, MCP, peers)
- `internal/hw/` — hardware detection
- `internal/process/` — process management
- `internal/router/` — routing (base, group, matrix, peer)
- `internal/server/` — API server (auth, metrics, filters, API)
- `internal/tailcat/transport.go` — tailcat transport
- `internal/store/store.go`, `internal/swaputil/events.go`
- Root: `llama-swap.go`, `go.mod`, `go.sum`, `Makefile`, `README.md`,
  `config.example.yaml`, `config-schema.json`
- `ui/` — consolidated dashboard (herd base + ranch additions)

## Divergence

- Fork point: `c6adf57` (upstream PR #940)
- Upstream remote: `https://github.com/mostlygeek/llama-swap.git`

## Merge notes

**`go.mod` / `go.sum`**: Do NOT blindly keep ours. Upstream adds new
dependencies; we add ours. Merge both lists, then run `go mod tidy`.

**Dry-run 2026-09-30**: Merging 102 upstream commits produced 31 conflicts,
all inside the 125-file patch surface above. No surprises.
