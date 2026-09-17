import { spawn } from "child_process";
import { mkdir, readdir, readFile, stat, writeFile } from "fs/promises";
import { dirname, join, extname, basename } from "path";

export interface F {
    p: string;
    sz: number;
    ext: string;
    rel: string;
}

export interface A {
    f: F;
    lang: string;
    domain: string;
    ring: number;
}

export async function scan(d: string, maxSz = 50 * 1024 * 1024): Promise<F[]> {
    const r: F[] = [];
    async function walk(dir: string, rel: string) {
        const es = await readdir(dir, { withFileTypes: true });
        for (const e of es) {
            const rp = join(rel, e.name);
            const ap = join(dir, e.name);
            if (e.isDirectory()) {
                await walk(ap, rp);
            } else {
                const s = await stat(ap);
                if (s.size > maxSz) continue;
                r.push({ p: ap, sz: s.size, ext: extname(e.name), rel: rp });
            }
        }
    }
    await walk(d, "");
    return r;
}

export async function hash(p: string): Promise<string> {
    const { createHash } = await import("crypto");
    const h = createHash("sha256");
    const b = await readFile(p);
    h.update(b);
    return h.digest("hex");
}

export function ring(a: A): string {
    const n = ["00-core", "01-kin", "02-domain", "03-archive", "04-quarantine"];
    return n[a.ring] || "04-quarantine";
}

export async function emit(src: string, tgt: string, a: A[]): Promise<void> {
    for (const x of a) {
        const d = join(tgt, ring(x), x.lang, x.domain);
        await mkdir(d, { recursive: true });
        const b = basename(x.f.p);
        await writeFile(join(d, b), await readFile(x.f.p));
    }
}

export async function runCmd(c: string, t = 10): Promise<{ o: string; e: string; r: number }> {
    return new Promise((res) => {
        const [cmd, ...args] = c.split(" ");
        const p = spawn(cmd, args, { timeout: t * 1000 });
        let o = "", e = "";
        p.stdout?.on("data", (d) => (o += d));
        p.stderr?.on("data", (d) => (e += d));
        p.on("close", (r) => res({ o, e, r: r || 0 }));
    });
}
