<script lang="ts">
	// The sovereign control surface. Every daemon the stack runs that serves a
	// page is a tab here, so "what is up" is one screen instead of a memory test
	// across 25xxx ports. The registry lives in lib/surfaces.ts.
	import { onDestroy, onMount } from "svelte";
	import { RefreshCw, ExternalLink, CircleAlert, CircleCheck, CircleHelp } from "@lucide/svelte";
	import { Badge } from "$lib/components/ui/badge/index.js";
	import { Button } from "$lib/components/ui/button/index.js";
	import * as Card from "$lib/components/ui/card/index.js";
	import { ScrollArea } from "$lib/components/ui/scroll-area/index.js";
	import * as Tabs from "$lib/components/ui/tabs/index.js";
	import {
		EMBEDDABLE_SURFACES,
		SURFACES,
		SURFACE_GROUPS,
		type Surface,
		type SurfaceHealth,
		probeAllSurfaces,
		UNKNOWN_HEALTH,
	} from "../lib/surfaces";

	const REFRESH_MS = 30_000;

	const inGroup = (group: string): Surface[] => SURFACES.filter((s) => s.group === group);

	let health = $state(new Map<string, SurfaceHealth>());
	let group = $state<string>(SURFACE_GROUPS[0]);
	let selectedId = $state<string>(EMBEDDABLE_SURFACES[0]?.id ?? SURFACES[0].id);
	let timer: ReturnType<typeof setInterval> | undefined;

	// A surface with a page of its own is embedded; an API-only surface has
	// nothing to frame, so it renders as a card describing what it serves.
	const selected = $derived(SURFACES.find((s) => s.id === selectedId) ?? SURFACES[0]);
	const embeddable = $derived(selected.kind === "ui" && selected.origin !== "");
	// Frame the service's own page, never its health endpoint — /health is
	// usually a JSON blob on a service whose UI lives at /.
	const frameUrl = $derived(
		selected.origin === ""
			? ""
			: `${selected.origin}${selected.pagePath ?? "/"}`,
	);

	function statusOf(id: string): SurfaceHealth {
		return health.get(id) ?? UNKNOWN_HEALTH;
	}

	// Status of the surface on the right, derived from the same map the list
	// reads so the header badge and the detail pane cannot disagree.
	const selectedStatus = $derived(statusOf(selected.id));

	function dotClass(status: SurfaceHealth["status"]): string {
		if (status === "up") return "bg-emerald-500";
		if (status === "down") return "bg-destructive";
		return "bg-muted-foreground/40";
	}

	async function refresh(): Promise<void> {
		health = await probeAllSurfaces(SURFACES);
	}

	onMount(() => {
		void refresh();
		timer = setInterval(() => void refresh(), REFRESH_MS);
	});

	onDestroy(() => {
		if (timer !== undefined) clearInterval(timer);
	});
</script>

<div class="flex h-full flex-col gap-4 p-4">
	<div class="flex items-center justify-between gap-4">
		<div>
			<h1 class="text-lg font-semibold">Surfaces</h1>
			<p class="text-muted-foreground text-sm">
				{SURFACES.length} services across {SURFACE_GROUPS.length} groups.
				{
					[...health.values()].filter((h) => h.status === "down").length
				}
				down.
			</p>
		</div>
		<Button variant="outline" size="sm" onclick={() => void refresh()}>
			<RefreshCw />
			Refresh
		</Button>
	</div>

	<Tabs.Root bind:value={group}>
		<Tabs.List>
			{#each SURFACE_GROUPS as g (g)}
				<Tabs.Trigger value={g}>{g}</Tabs.Trigger>
			{/each}
		</Tabs.List>
	</Tabs.Root>

	<div class="grid min-h-0 flex-1 gap-4 lg:grid-cols-[22rem_1fr]">
		<Card.Root class="min-h-0 overflow-hidden py-0">
			<ScrollArea class="h-full">
				<ul class="divide-border divide-y">
					{#each inGroup(group) as surface (surface.id)}
						{@const status = statusOf(surface.id)}
						<li>
							<button
								type="button"
								class="hover:bg-muted/50 flex w-full items-start gap-2 px-3 py-2 text-left {surface.id ===
								selectedId
									? 'bg-muted'
									: ''}"
								onclick={() => (selectedId = surface.id)}
							>
								<span class="mt-1.5 size-2 shrink-0 rounded-full {dotClass(status.status)}"></span>
								<span class="min-w-0 flex-1">
									<span class="flex items-center gap-2">
										<span class="truncate text-sm font-medium">{surface.label}</span>
										{#if surface.kind === "api"}
											<Badge variant="outline" class="h-4 px-1 text-[10px]">api</Badge>
										{/if}
									</span>
									<span class="text-muted-foreground block truncate text-xs">
										{surface.description}
									</span>
									{#if status.status !== "unknown" && status.detail}
										<span class="text-muted-foreground/70 block truncate text-[11px]">
											{status.detail}{status.latencyMs !== undefined ? ` · ${status.latencyMs}ms` : ""}
										</span>
									{/if}
								</span>
							</button>
						</li>
					{/each}
				</ul>
			</ScrollArea>
		</Card.Root>

		<Card.Root class="flex min-h-0 flex-col gap-3 overflow-hidden py-0">
			<Card.Header class="flex flex-row items-start justify-between gap-3 border-b">
				<div class="min-w-0">
					<Card.Title class="truncate text-base">{selected.label}</Card.Title>
					<Card.Description class="truncate">
						{selected.description}
					</Card.Description>
				</div>
				<div class="flex shrink-0 items-center gap-2">
					{#if selectedStatus.status === "up"}
						<Badge variant="secondary"><CircleCheck />{selectedStatus.latencyMs}ms</Badge>
					{:else if selectedStatus.status === "down"}
						<Badge variant="destructive"><CircleAlert />{selectedStatus.detail}</Badge>
					{:else}
						<Badge variant="outline"><CircleHelp />unknown</Badge>
					{/if}
					{#if selected.origin !== ""}
						<a
							href={frameUrl}
							target="_blank"
							rel="noreferrer noopener"
							class="text-muted-foreground hover:text-foreground inline-flex size-7 items-center justify-center"
							title="Open in a new tab"
						>
							<ExternalLink class="size-4" />
						</a>
					{/if}
				</div>
			</Card.Header>

			<Card.Content class="min-h-0 flex-1 p-0">
				{#if embeddable}
					<iframe
						src={frameUrl}
						title={selected.label}
						class="size-full border-0"
						referrerpolicy="no-referrer"
						allow="clipboard-read; clipboard-write"
					></iframe>
				{:else}
					<dl class="grid gap-3 p-4 text-sm sm:grid-cols-2">
						<div>
							<dt class="text-muted-foreground text-xs uppercase tracking-wider">Kind</dt>
							<dd>{selected.kind === "ui" ? "Web UI" : "API only — no page to embed"}</dd>
						</div>
						<div>
							<dt class="text-muted-foreground text-xs uppercase tracking-wider">Daemon</dt>
							<dd>{selected.daemon ?? "—"}</dd>
						</div>
						<div>
							<dt class="text-muted-foreground text-xs uppercase tracking-wider">Origin</dt>
							<dd class="font-mono text-xs">
								{selected.origin === "" ? "same-origin (this app)" : selected.origin}
							</dd>
						</div>
						<div>
							<dt class="text-muted-foreground text-xs uppercase tracking-wider">Health path</dt>
							<dd class="font-mono text-xs">{selected.healthPath ?? "/"}</dd>
						</div>
						<div>
							<dt class="text-muted-foreground text-xs uppercase tracking-wider">Page path</dt>
							<dd class="font-mono text-xs">{selected.pagePath ?? "/"}</dd>
						</div>
					</dl>
				{/if}
			</Card.Content>
		</Card.Root>
	</div>
</div>
