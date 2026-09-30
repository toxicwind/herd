// surfaces: the inventory of every browser-reachable service in the sovereign
// stack, so the master dashboard can present the whole stack as one set of
// tabs instead of N half-wired dashboards that each know about one daemon.
//
// Provenance: ports and health paths are transcribed from the `[daemons.*]`
// blocks in `sovereign/pitchfork.toml`, which is the authoritative service
// list. Daemon names are carried through verbatim so a tab can name the thing
// that has to be running for it to answer.
//
// A surface is `ui` when something serves an actual page, and `api` when the
// port only speaks HTTP. Embedding an api surface in a frame would just render
// raw JSON, so those are listed with live health and open in a new tab instead.
// The distinction is about what a human gets out of the tab, not about whether
// the service exists.

export type SurfaceKind = "ui" | "api";

export interface Surface {
	/** Stable id, also the tab value. */
	id: string;
	label: string;
	/** Grouping section in the tab strip. */
	group: string;
	/** Absolute origin. Same-origin for herd, which this app already proxies. */
	origin: string;
	kind: SurfaceKind;
	/** The pitchfork daemon that serves it, when there is one. */
	daemon?: string;
	/** Path probed for health. Defaults to "/". */
	healthPath?: string;
	/**
	 * Path embedded in the tab's iframe. Distinct from `healthPath`: a service
	 * is usually healthy at `/health` but serves its page at `/`, and framing
	 * the health endpoint shows raw JSON instead of the app. Defaults to "/".
	 */
	pagePath?: string;
	/** Shown in the tab's tooltip and in the service detail. */
	description: string;
}

const loopback = (port: number): string => `http://127.0.0.1:${port}`;

export const SURFACE_GROUPS = [
	"Models",
	"Fleet",
	"Mesh",
	"Search",
	"Ops",
	"Automation",
] as const;

export type SurfaceGroup = (typeof SURFACE_GROUPS)[number];

export const SURFACES: readonly Surface[] = [
	// ── Models & inference ────────────────────────────────────────────────
	{
		id: "herd",
		label: "Herd",
		group: "Models",
		// herd is the llama-swap-shaped API this dashboard already talks to
		// through apiBase, so it has no separate page to embed.
		origin: "",
		kind: "api",
		daemon: "herd",
		healthPath: "/health",
		description: "llama-swap: the local model gateway this dashboard drives.",
	},
	{
		id: "flock",
		label: "Flock",
		group: "Models",
		origin: loopback(25193),
		kind: "api",
		daemon: "flock",
		healthPath: "/health",
		description: "Cloud provider gateway — the other half of the model plane.",
	},
	{
		id: "beellama",
		label: "Beellama",
		group: "Models",
		origin: loopback(25122),
		kind: "ui",
		daemon: "beellama-fast",
		healthPath: "/health",
		description: "llama.cpp server front end — full llama-server chat UI.",
	},
	{
		id: "model-guard",
		label: "Model Guard",
		group: "Models",
		origin: loopback(25101),
		kind: "api",
		daemon: "model-guard",
		healthPath: "/v1/models",
		description: "Proxies :25100 and rewrites chat bodies per model constraints.",
	},
	{
		id: "rust-web",
		label: "Effusion Labs",
		group: "Models",
		origin: loopback(25201),
		kind: "ui",
		daemon: "rust-web",
		healthPath: "/health",
		description: "effusionlabs-os — the algo console.",
	},
	{
		id: "ml-serve",
		label: "ML Serve",
		group: "Models",
		origin: loopback(25180),
		kind: "api",
		daemon: "ml-serve",
		healthPath: "/health",
		description: "Model serving for the algo side.",
	},

	// ── Fleet & agents ────────────────────────────────────────────────────
	{
		id: "tau",
		label: "Tau",
		group: "Fleet",
		origin: loopback(25111),
		kind: "ui",
		daemon: "tau",
		description: "The agent engine this session is running inside.",
	},
	{
		id: "agent-viewer",
		label: "Agent Viewer",
		group: "Fleet",
		origin: "http://127.0.0.1:6080",
		kind: "ui",
		daemon: "agent-viewer",
		description: "noVNC view into the agent desktop.",
	},
	{
		id: "hindsight",
		label: "Hindsight",
		group: "Fleet",
		origin: loopback(25117),
		kind: "ui",
		daemon: "hindsight",
		healthPath: "/health",
		description: "Memory / recall service for the agent fleet.",
	},
	{
		id: "kimi-code",
		label: "Kimi Code",
		group: "Fleet",
		origin: loopback(25126),
		kind: "api",
		daemon: "kimi-code",
		healthPath: "/health",
		description: "Kimi coding agent service.",
	},
	{
		id: "kimi-audit",
		label: "Kimi Audit",
		group: "Fleet",
		origin: loopback(25116),
		kind: "ui",
		daemon: "kimi-audit-dash",
		healthPath: "/health",
		description: "Audit dashboard for the kimi auto runs.",
	},
	{
		id: "byte-vision",
		label: "Byte Vision",
		group: "Fleet",
		origin: loopback(25121),
		kind: "api",
		daemon: "byte-vision",
		healthPath: "/health",
		description: "Vision/OCR service.",
	},
	{
		id: "oracle-core",
		label: "Oracle",
		group: "Fleet",
		origin: loopback(25151),
		kind: "api",
		daemon: "oracle-core",
		healthPath: "/health",
		description: "Oracle market core.",
	},
	{
		id: "coyote",
		label: "Coyote",
		group: "Fleet",
		origin: loopback(25143),
		kind: "api",
		daemon: "coyote",
		healthPath: "/health",
		description: "Coyote service.",
	},
	{
		id: "toolcall-llm",
		label: "Toolcall LLM",
		group: "Fleet",
		origin: loopback(25152),
		kind: "api",
		daemon: "toolcall-llm",
		healthPath: "/health",
		description: "Tool-calling LLM shim.",
	},

	// ── Mesh & routing ────────────────────────────────────────────────────
	{
		id: "gatehouse",
		label: "Gatehouse",
		group: "Mesh",
		origin: loopback(25127),
		kind: "ui",
		daemon: "gatehouse",
		healthPath: "/health",
		description: "MCP gateway and its web control panel.",
	},
	{
		id: "mesh-hub",
		label: "Mesh Hub",
		group: "Mesh",
		origin: loopback(25115),
		kind: "api",
		daemon: "mesh-hub",
		healthPath: "/health",
		description: "Agent mesh hub.",
	},
	{
		id: "mesh-landing",
		label: "Mesh Landing",
		group: "Mesh",
		origin: loopback(25207),
		kind: "ui",
		daemon: "mesh-landing",
		healthPath: "/health",
		description: "Landing page for the mesh fleet.",
	},
	{
		id: "vansrouter",
		label: "VansRouter",
		group: "Mesh",
		origin: loopback(20128),
		kind: "ui",
		daemon: "vansrouter",
		healthPath: "/api/health",
		description: "Model router control plane.",
	},
	{
		id: "yote",
		label: "Yote",
		group: "Mesh",
		origin: loopback(25102),
		kind: "api",
		daemon: "yote",
		healthPath: "/health",
		description: "Yote fleet bus.",
	},
	{
		id: "sovereign-chat",
		label: "Sovereign Chat",
		group: "Mesh",
		origin: loopback(25120),
		kind: "ui",
		daemon: "sovereign-chat",
		healthPath: "/health",
		description: "First-class fleet chat plane.",
	},
	{
		id: "matter",
		label: "Matter",
		group: "Mesh",
		origin: loopback(25209),
		kind: "api",
		daemon: "matter-server",
		healthPath: "/health",
		description: "Matter server.",
	},
	{
		id: "nginx",
		label: "Nginx",
		group: "Mesh",
		origin: loopback(25208),
		kind: "api",
		daemon: "nginx",
		description: "Front reverse proxy for the stack.",
	},

	// ── Search & knowledge ────────────────────────────────────────────────
	{
		id: "search-ui",
		label: "Search",
		group: "Search",
		origin: loopback(25114),
		kind: "ui",
		daemon: "search-ui",
		description: "Code and document search UI.",
	},
	{
		id: "search-api",
		label: "Search API",
		group: "Search",
		origin: loopback(25112),
		kind: "api",
		daemon: "search-api",
		healthPath: "/health",
		description: "Backend behind the search UI.",
	},
	{
		id: "codebase-memory",
		label: "Codebase Memory",
		group: "Search",
		origin: loopback(25195),
		kind: "api",
		daemon: "codebase-memory",
		description: "Repository memory index.",
	},
	{
		id: "qdrant",
		label: "Qdrant",
		group: "Search",
		origin: loopback(25133),
		kind: "api",
		daemon: "qdrant",
		description: "Vector store for recall and memory.",
	},
	{
		id: "hf-downloader",
		label: "HF Downloader",
		group: "Search",
		origin: loopback(25106),
		kind: "api",
		daemon: "hf-downloader",
		healthPath: "/api/health",
		description: "Hugging Face asset fetcher.",
	},

	// ── Ops & observability ───────────────────────────────────────────────
	{
		id: "openfang",
		label: "OpenFang",
		group: "Ops",
		origin: loopback(25196),
		kind: "api",
		daemon: "openfang",
		healthPath: "/api/health",
		description: "OpenFang runtime.",
	},
	{
		id: "openfang-front",
		label: "OpenFang UI",
		group: "Ops",
		origin: loopback(25103),
		kind: "ui",
		daemon: "openfang-front",
		healthPath: "/api/health",
		description: "OpenFang front end.",
	},
	{
		id: "grafana",
		label: "Grafana",
		group: "Ops",
		origin: loopback(25110),
		kind: "ui",
		daemon: "grafana",
		healthPath: "/api/health",
		description: "Dashboards and alerting.",
	},
	{
		id: "prometheus",
		label: "Prometheus",
		group: "Ops",
		origin: loopback(25105),
		kind: "ui",
		daemon: "prometheus",
		healthPath: "/-/healthy",
		description: "Metrics store and query UI.",
	},
	{
		id: "ralph",
		label: "Ralph",
		group: "Ops",
		origin: loopback(25194),
		kind: "ui",
		daemon: "ralph-dashboard",
		healthPath: "/api/health",
		description: "Ralph loop dashboard.",
	},
	{
		id: "bench-radar",
		label: "Bench Radar",
		group: "Ops",
		origin: loopback(25181),
		kind: "ui",
		daemon: "bench-radar",
		healthPath: "/health",
		description: "Model benchmark results.",
	},
	{
		id: "telemetry",
		label: "PCIe Moe",
		group: "Ops",
		origin: loopback(25219),
		kind: "api",
		daemon: "pcie-moe-telemetry",
		healthPath: "/api/status",
		description: "PCIe / MoE accelerator telemetry.",
	},
	{
		id: "node-exporter",
		label: "Node Exporter",
		group: "Ops",
		origin: loopback(25211),
		kind: "api",
		daemon: "node-exporter",
		healthPath: "/metrics",
		description: "Host metrics.",
	},
	{
		id: "sovereign-exporter",
		label: "Sovereign Exporter",
		group: "Ops",
		origin: loopback(25213),
		kind: "api",
		daemon: "sovereign-exporter",
		healthPath: "/metrics",
		description: "Stack-level Prometheus exporter.",
	},
	{
		id: "browser-keeper",
		label: "Browser Keeper",
		group: "Ops",
		origin: loopback(9223),
		kind: "api",
		daemon: "browser-keeper",
		healthPath: "/",
		description: "Headless Chrome DevTools endpoint.",
	},
	{
		id: "files",
		label: "Files",
		group: "Ops",
		origin: loopback(34567),
		kind: "ui",
		daemon: "files",
		healthPath: "/health",
		description: "File server.",
	},

	// ── Automation & integration ──────────────────────────────────────────
	{
		id: "awrawr-mcp",
		label: "Awrawr MCP",
		group: "Automation",
		origin: loopback(25198),
		kind: "api",
		daemon: "awrawr-mcp",
		description: "Personal assistant MCP surface.",
	},
	{
		id: "awrawr-ws-exec",
		label: "Awrawr Exec",
		group: "Automation",
		origin: loopback(25204),
		kind: "api",
		daemon: "awrawr-ws-exec",
		description: "Websocket exec channel.",
	},
	{
		id: "whatsapp-mcp",
		label: "WhatsApp",
		group: "Automation",
		origin: loopback(25146),
		kind: "api",
		daemon: "whatsapp-mcp",
		healthPath: "/health",
		description: "WhatsApp bridge.",
	},
	{
		id: "buildsrv",
		label: "Build Server",
		group: "Automation",
		origin: loopback(25148),
		kind: "ui",
		daemon: "buildsrv",
		healthPath: "/health",
		description: "Forward-only Rust/Go/Bun build daemon.",
	},
	{
		id: "paper-poller",
		label: "Paper Poller",
		group: "Automation",
		origin: loopback(25149),
		kind: "api",
		daemon: "paper-poller",
		healthPath: "/ready",
		description: "arXiv/alphaXiv search racer.",
	},
	{
		id: "keypool",
		label: "Keypool",
		group: "Automation",
		origin: loopback(25109),
		kind: "api",
		daemon: "keypool",
		healthPath: "/health",
		description: "Rotating API key pool.",
	},
	{
		id: "null-g-proxy",
		label: "Null-G Proxy",
		group: "Automation",
		origin: loopback(25107),
		kind: "api",
		daemon: "null-g-proxy",
		healthPath: "/health",
		description: "Null-gravity egress proxy.",
	},
	{
		id: "stream-broker",
		label: "Stream Broker",
		group: "Automation",
		origin: loopback(25215),
		kind: "api",
		daemon: "sovereign-stream-broker",
		description: "Fleet event stream broker.",
	},
	{
		id: "nim-kimi",
		label: "NIM Kimi",
		group: "Automation",
		origin: loopback(25163),
		kind: "api",
		daemon: "nim-kimi-sidecar",
		healthPath: "/health",
		description: "NIM sidecar for kimi models.",
	},
	{
		id: "kimi-shim",
		label: "Kimi Shim",
		group: "Automation",
		origin: loopback(25153),
		kind: "api",
		daemon: "kimi-auto-shim",
		healthPath: "/health",
		description: "Compatibility shim for the kimi auto stack.",
	},
	{
		id: "boundless",
		label: "Boundless",
		group: "Automation",
		origin: loopback(25197),
		kind: "ui",
		daemon: "boundless",
		description: "Boundless web app.",
	},
];

/** Surfaces that render a page, in tab order. These are the embeddable ones. */
export const EMBEDDABLE_SURFACES: readonly Surface[] = SURFACES.filter(
	(surface) => surface.kind === "ui" && surface.origin !== "",
);

export interface SurfaceHealth {
	status: "up" | "down" | "unknown";
	/** Round-trip time in ms; undefined when the probe did not complete. */
	latencyMs?: number;
	/** HTTP status, or the transport-level failure reason. */
	detail: string;
}

export const UNKNOWN_HEALTH: SurfaceHealth = { status: "unknown", detail: "not probed" };

const PROBE_TIMEOUT_MS = 3_000;
const PROBE_CONCURRENCY = 12;

/**
 * Probe one surface. `mode: "no-cors"` is deliberate: these are other origins,
 * so a full fetch is opaque unless every one of them sets CORS headers. A
 * no-cors request still resolves for a reachable server and still rejects for a
 * dead one, which is exactly the signal a health badge needs — the response
 * body is never read.
 */
export async function probeSurface(surface: Surface): Promise<SurfaceHealth> {
	if (surface.origin === "") {
		// Same-origin surfaces are already covered by the dashboard's own
		// connection state; probing them here would double-count herd.
		return { status: "up", detail: "same origin" };
	}
	const url = `${surface.origin}${surface.healthPath ?? "/"}`;
	const started = performance.now();
	try {
		const response = await fetch(url, {
			mode: "no-cors",
			cache: "no-store",
			signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
		});
		return {
			status: "up",
			latencyMs: Math.round(performance.now() - started),
			detail: `HTTP ${response.status}`,
		};
	} catch (error) {
		// A no-cors probe of a live server reports "opaque"; a dead one throws.
		// Anything reaching here is a transport failure worth naming exactly,
		// because "down" with no reason is the least actionable badge there is.
		return {
			status: "down",
			latencyMs: Math.round(performance.now() - started),
			detail: error instanceof Error ? error.message : String(error),
		};
	}
}

/** Probe every surface with bounded concurrency, preserving registry order. */
export async function probeAllSurfaces(
	surfaces: readonly Surface[] = SURFACES,
): Promise<Map<string, SurfaceHealth>> {
	const results = new Map<string, SurfaceHealth>();
	let cursor = 0;

	async function worker(): Promise<void> {
		while (cursor < surfaces.length) {
			const surface = surfaces[cursor++];
			if (!surface) continue;
			results.set(surface.id, await probeSurface(surface));
		}
	}

	const workers = Array.from(
		{ length: Math.min(PROBE_CONCURRENCY, surfaces.length) },
		() => worker(),
	);
	await Promise.all(workers);
	return results;
}
