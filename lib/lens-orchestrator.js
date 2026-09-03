/**
 * Lens Orchestrator - First-Class Agentic Perception Layer
 * Auto-discovers lens_*.js modules from src/_11ty/lenses/
 * @version 2.0.0-agentic
 */
const fs = require('fs').promises;
const path = require('path');
const LENS_DIR = path.resolve(__dirname, '../src/_11ty/lenses');
class LensOrchestrator {
  constructor(opts = {}) {
    this.lensDir = opts.lensDir || LENS_DIR;
    this.lenses = new Map();
  }
  async discover() {
    const entries = await fs.readdir(this.lensDir).catch(() => []);
    const lensFiles = entries.filter(f => f.startsWith('lens_') && f.endsWith('.js'));
    for (const file of lensFiles) {
      try {
        const mod = require(path.join(this.lensDir, file));
        if (mod.name && typeof mod.analyze === 'function') this.lenses.set(mod.name, mod);
      } catch (e) { console.warn(`[lens] Failed to load ${file}: ${e.message}`); }
    }
    console.log(`[lens] Discovered ${this.lenses.size} lens profiles`);
    return Array.from(this.lenses.values());
  }
  async analyze(lensName, content, meta = {}) {
    const lens = this.lenses.get(lensName);
    if (!lens) throw new Error(`Lens "${lensName}" not discovered`);
    return await lens.analyze(content, meta);
  }
  async analyzeAll(content, meta = {}) {
    const results = {};
    for (const [name, lens] of this.lenses) results[name] = await this.analyze(name, content, meta);
    return results;
  }
}
module.exports = { LensOrchestrator };
