# ranch dashboard (`ui/`)

The ranch control UI: one Svelte single-page app over **herd** (local models)
and **flock** (cloud providers). Pure client — no backend, no database, no
server of its own. It talks to a llama-swap-shaped HTTP API over a single
configurable base URL.

> **Read the provenance first.** This is llama-swap's web UI, adopted into the
> ranch. It is not a UI written for the ranch, and its route names, vocabulary
> and API surface are upstream's.

---

## Provenance

Two hops, both verifiable in git:

```
  mostlygeek/llama-swap  ──►  herd  ──►  ranch/ui
        (the UI)          (carried it)   commit d39a6f8
```

`d39a6f8` — *"ranch: adopt herd UI as the ranch dashboard (apiBase-configurable,
vite outDir dist)"*. It created `ui/` at the top of this repo; the dashboard sits at the ranch root as a sibling of `herd/`, not
a child of it. The upstream fingerprints are still everywhere in `src/`:

| Evidence | Where |
| :--- | :--- |
| `<title>llama-swap</title>` | `index.html` |
| `appTitle` defaults to `"llama-swap"` | `src/stores/theme.ts` |
| MCP client for "llama-swap's own `/api/mcp`" | `src/lib/agentTools.ts` |
| Docs agent answering questions *about llama-swap* | `src/lib/prompts/docsAgent.ts`, `src/cli/` |
| `Exported from [llama-swap](…)` | `src/lib/activityExport.ts` |
| Links to mostlygeek/llama-swap issues & discussions | `src/routes/Performance.svelte` |
| Dev proxy defaults to llama-swap's `localhost:8080` | `vite.config.ts` |

The upstream commit this forked from is **not recorded anywhere in the tree**.
If a llama-swap feature matters to you, check upstream release notes rather
than assuming a version.

The ranch-specific delta is genuinely small and concentrated in two files:
`src/lib/apiBase.ts` (detach the API base from the origin) and `vite.config.ts`
(`base: "/ui/"`, `outDir: dist`). Everything else is upstream. In particular the
roadmap the earlier README listed — a flock panel, a unified local+cloud model
view — is **not implemented**; `/models` and `/playground` are llama-swap's and
know nothing about flock. Treat those as open, not pending.

---

## Stack

| | |
| :--- | :--- |
| framework | Svelte 5 (`mount()`, runes) |
| build | Vite 8, `base: "/ui/"` |
| styling | Tailwind 4 via `@tailwindcss/vite` → `src/index.css` |
| components | shadcn-svelte over `bits-ui`; aliases in `components.json` (zinc base) |
| routing | `svelte-spa-router`, lazy per route |
| markdown | `unified` + `remark-math` / `rehype-katex` / `highlight.js` |
| tables | `@tanstack/table-core` · panels `paneforge` · icons `@lucide/svelte` |
| tests | `vitest`, colocated `*.test.ts` |
| manifest | `package.json` name `ranch-dashboard`, `private`, ESM |

`.npmrc` sets `legacy-peer-deps=true`. Keep it — a fresh install fails on peer
ranges without it.

---

## Commands

Every script in `package.json`. There is no Makefile, and **no `dev` script** —
the dev server is `start`.

| Command | Runs | Use it to |
| :--- | :--- | :--- |
| `bun run start` | `vite` | dev server |
| `bun run build` | `vite build --emptyOutDir` | produce `dist/` |
| `bun run preview` | `vite preview` | serve the built `dist/` |
| `bun run check` | `svelte-check --tsconfig ./tsconfig.json` | type + template diagnostics |
| `bun run test` | `vitest run` | suite, once |
| `bun run test:watch` | `vitest` | suite, watching |

```sh
bun install
VITE_HERD_API=http://127.0.0.1:25100 bun run start
```

The dev server binds `0.0.0.0` with `allowedHosts: true` — `vite.config.ts`
jokes about it. Fine on a tailnet; do not expose it.

---

## Pointing it at an API

`src/lib/apiBase.ts` resolves `API_BASE` once, at load, first match wins:

| Order | Source | Set by |
| :---: | :--- | :--- |
| 1 | `window.__HERD_API__` | a script tag before the bundle loads |
| 2 | `import.meta.env.VITE_HERD_API` | the build environment |
| 3 | `""` — same origin | default; the old embedded-in-herd behaviour |

```js
window.__HERD_API__ = "http://127.0.0.1:25100";
```

Everything goes through the exported `api(path)` helper, so this one value
redirects the whole app.

**Do not confuse it with `LLAMA_SWAP_URL`.** That is dev-server plumbing: Vite
proxies `/api`, `/logs`, `/upstream`, `/unload`, `/v1` and `/sdapi` to
`LLAMA_SWAP_URL` (default `http://localhost:8080`), which is what lets the dev
server work with no `VITE_HERD_API` build. It has no effect on a production
bundle; `VITE_HERD_API` / `__HERD_API__` is what the bundle actually calls.

---

## Layout

| Path | |
| :--- | :--- |
| `src/main.ts` | entrypoint — mounts `App` |
| `src/App.svelte` | shell + route table |
| `src/routes/` | one component per route |
| `src/lib/` | the bulk: API clients, chat/playground state, markdown, agent tools, prompts |
| `src/lib/components/ui/` | shadcn-svelte primitives |
| `src/components/` | widgets — activity table, model cards, playground |
| `src/stores/` | Svelte stores — api, theme, playground, route, sidebar, logs |
| `src/cli/` | standalone Node eval harness — **not** in the bundle |

180 `.svelte` and 105 `.ts` files — 104 of the `.ts` under `src/`, the last
being `vite.config.ts`. Every route is lazily imported via
`wrap({ asyncComponent, loadingComponent })`, so each becomes its own chunk
fetched on first visit.

| Route | Component |
| :--- | :--- |
| `/`, `/activity`, `*` | `Activity.svelte` |
| `/models`, `/models/:id` | `ModelsDash.svelte`, `ModelDetail.svelte` |
| `/logs` | `LogViewer.svelte` |
| `/settings` | `Settings.svelte` |
| `/performance` | `Performance.svelte` |
| `/hardware` | `Hardware.svelte` |
| `/tailcat` | `Tailcat.svelte` |
| `/help` | `Help.svelte` |
| `/playground` | `PlaygroundStub.svelte` — **a stub**, not the chat playground |

That last row is the one people trip on: `/playground` renders a placeholder.
The real playground exists as a component but is not routed.

---

## Build and serving

`bun run build` writes `dist/`, with `base: "/ui/"` — it expects to be served
under a `/ui/` prefix. `dist/` is untracked and **is** gitignored, by the
repo-root `.gitignore` (`dist/`, line 18), so it does not clutter
`git status`; rebuild it rather than editing it.

Two Vite plugins earn their place, and both are load-bearing:

- `stripKatexFontFallbacks` rewrites `katex.min.css` to drop the `woff`/`ttf`
  `@font-face` fallbacks browsers never fetch.
- `compression` is pinned to `algorithms: ["brotliCompress"]`. The comment
  records why: the plugin silently ignores an unknown key and runs *both* gzip
  and brotli, so a second pass re-compresses files the exclude list already
  rejected.

**Nothing supervises this app.** No pitchfork unit, no `location /ui/` in
`ops/nginx/nginx.conf`, no service script in `stack/services/`. It builds and
previews locally; serving `dist/` is a manual step.

---

## Tests

26 files, 384 tests, colocated beside the code. Vitest reads `vite.config.ts`;
there is no separate vitest config.

**The suite is red as of 2026-09-26**: `bun run test` reports 328 passing, 56
failing across 5 files — `activityExport`, `chatApi`, `chatApiStream`, `types`,
`stores/playground` — largely `TypeError: <export> is not a function` left by a
store refactor. Treat a non-zero exit as the current baseline, not as
something you broke.

---

## The eval harness

`src/cli/` is a standalone Node harness for the Help docs agent — `ask`, `eval`
and `judge` — with its own history log. It imports the *same* `agentLoop.ts`,
`chatApi.ts` and `agentTools.ts` the browser runs, so it measures what ships.
It is reachable through no `package.json` script, and its `USAGE` string still
advertises `npm run agent --`, which matches nothing in this manifest. Run it
directly:

```sh
bun run src/cli/docsAgent.ts ask "how do I configure a model?"
```

Its default case and results directories resolve to
`ranch/evals/docs-agent/{cases,runs}` — **that directory does not exist in this
tree**, so `eval` and `judge` have no defaults to work from until it is
restored. It reads `LLAMA_SWAP_URL`, `DOCS_AGENT_MODEL` and
`DOCS_AGENT_JUDGE_MODEL`.

---

## See also

- [`../herd/`](../herd/) — where this UI came from
- [`../flock/`](../flock/) — the cloud side it does not yet reach
