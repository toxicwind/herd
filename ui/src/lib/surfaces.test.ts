import { describe, expect, it } from "vitest";
import {
	EMBEDDABLE_SURFACES,
	SURFACES,
	SURFACE_GROUPS,
	probeAllSurfaces,
	probeSurface,
	type Surface,
} from "./surfaces";

// The registry is transcribed from pitchfork.toml by hand, so the failure mode
// is a typo: a duplicate tab id, a port on the wrong group, a "ui" surface with
// no origin (which would render an empty frame), or an id that does not match
// the label. These assert the invariants that make the tab strip usable.

// A required field the assertions never read is one more thing to update when
// Surface grows, so the fixtures build through a factory instead of repeating
// the whole shape.
const surface = (overrides: Partial<Surface> & Pick<Surface, "id">): Surface => ({
	label: overrides.id.toUpperCase(),
	group: "Ops",
	origin: "",
	kind: "api",
	description: "test surface",
	...overrides,
});

describe("surface registry", () => {
	it("has unique ids", () => {
		const ids = SURFACES.map((surface) => surface.id);
		expect(new Set(ids).size).toBe(ids.length);
	});

	it("assigns every surface to a declared group", () => {
		const groups = new Set<string>(SURFACE_GROUPS);
		for (const surface of SURFACES) {
			expect(groups).toContain(surface.group);
		}
	});

	it("gives every embeddable surface an absolute origin", () => {
		for (const surface of EMBEDDABLE_SURFACES) {
			expect(surface.origin).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
		}
	});

	it("pins every origin to a port pitchfork actually declares", () => {
		// Most of the stack is in the 25xxx block. These are the deliberate
		// exceptions, each owned by a daemon in pitchfork.toml: 5900/6080 are
		// VNC and noVNC, 9223 is Chrome DevTools, 20128 is vansrouter's own
		// port, 34567 is the file server. Anything else is a transcription slip.
		const auxiliaryPorts = new Set([5900, 6080, 9223, 20128, 34567]);
		for (const surface of SURFACES) {
			const port = surface.origin.match(/:(\d+)$/)?.[1];
			if (!port) continue;
			const value = Number(port);
			const inStackBlock = value >= 25100 && value < 26000;
			expect(
				inStackBlock || auxiliaryPorts.has(value),
				`${surface.id} uses undeclared port ${port}`,
			).toBe(true);
		}
	});

	it("lists no two surfaces on the same origin", () => {
		const origins = SURFACES.map((surface) => surface.origin).filter(Boolean);
		expect(new Set(origins).size).toBe(origins.length);
	});

	it("treats herd as same-origin rather than embedding an empty frame", () => {
		const herd = SURFACES.find((surface) => surface.id === "herd");
		expect(herd?.origin).toBe("");
		expect(EMBEDDABLE_SURFACES.map((s) => s.id)).not.toContain("herd");
	});

	it("keeps surfaces in registry order when probing", async () => {
		const surfaces: Surface[] = [surface({ id: "a" }), surface({ id: "b" })];
		const health = await probeAllSurfaces(surfaces);
		expect([...health.keys()]).toEqual(["a", "b"]);
	});

	it("reports a same-origin surface as up without a request", async () => {
		const health = await probeSurface(surface({ id: "a" }));
		expect(health.status).toBe("up");
	});
});
