#!/usr/bin/env python3
"""Phase 3 herd retirement patches: config.go, server.go, api.go."""
import sys

def patch(path, pairs):
    s = open(path).read()
    for old, new in pairs:
        if old not in s:
            if new in s:
                print(f"SKIP (already applied) in {path}: {old[:50]!r}")
                continue
            print(f"FATAL: anchor missing in {path}: {old[:70]!r}")
            sys.exit(1)
        s = s.replace(old, new, 1)
    open(path, "w").write(s)
    print(f"patched {path}")

# ---------------- config.go ----------------
patch("internal/config/config.go", [
    (
        "// AstMatrixConfig configures the AST Matrix cloud router.\ntype AstMatrixConfig struct {",
        "// AstMatrixConfig configured the AST Matrix cloud router.\n"
        "//\n"
        "// RETIRED 2026-09-17: the in-process astmatrix.Router was replaced by Flock\n"
        "// delegation (see FlockConfig). The struct survives only so old config files\n"
        "// still parse; the server no longer wires it.\n"
        "type AstMatrixConfig struct {",
    ),
    (
        "\t// AstMatrix configures the AST Matrix cloud router.\n"
        "\t// When enabled, cloud model requests are routed through the matrix\n"
        "\t// to remote providers (openrouter, nvidia, groq, google, etc.).\n"
        '\tAstMatrix *AstMatrixConfig `yaml:"astMatrix"`\n'
        "}",
        "\t// AstMatrix configures the AST Matrix cloud router.\n"
        "\t// When enabled, cloud model requests are routed through the matrix\n"
        "\t// to remote providers (openrouter, nvidia, groq, google, etc.).\n"
        "\t//\n"
        "\t// RETIRED 2026-09-17: ignored by the server. Configure flock: instead.\n"
        '\tAstMatrix *AstMatrixConfig `yaml:"astMatrix"`\n'
        "\n"
        "\t// Flock delegates cloud-model serving to Flock (:8000), the unified\n"
        "\t// multi-provider remote-API/completions subsystem. Replaces astMatrix.\n"
        '\tFlock *FlockConfig `yaml:"flock"`\n'
        "}\n"
        "\n"
        "// FlockConfig configures the Flock cloud delegation.\n"
        "//\n"
        "// herd :25100 stays the front door; any model Flock serves (plus the\n"
        "// configured aliases) is reverse-proxied to Flock's /v1 with herd's own\n"
        "// FLOCK_API_KEY. Provider pools, health, circuits and retries live in Flock.\n"
        "type FlockConfig struct {\n"
        '\tEnabled  bool              `yaml:"enabled"`\n'
        '\tBaseURL  string            `yaml:"baseUrl"`\n'
        '\tKeyEnv   string            `yaml:"keyEnv"`\n'
        '\tModelMap map[string]string `yaml:"modelMap"`\n'
        "}\n"
        "\n"
        "func (f *FlockConfig) Defaults() {\n"
        '\tif f.BaseURL == "" {\n'
        '\t\tf.BaseURL = "http://127.0.0.1:8000"\n'
        "\t}\n"
        '\tif f.KeyEnv == "" {\n'
        '\t\tf.KeyEnv = "FLOCK_API_KEY"\n'
        "\t}\n"
        "}",
    ),
])

# ---------------- api.go (/v1/models discovery) ----------------
patch("internal/server/api.go", [
    (
        "\tfor peerID, peer := range s.cfg.Peers {\n"
        "\t\tfor _, modelID := range peer.Models {\n"
        "\t\t\tmodelIDs[modelID] = struct{}{}\n"
        '\t\t\tdata = append(data, newRecord(modelID, peerID+": "+modelID, "", map[string]any{"peerID": peerID}, config.ModelCapConfig{}, "unloaded"))\n'
        "\t\t}\n"
        "\t}\n",
        "\tfor peerID, peer := range s.cfg.Peers {\n"
        "\t\tfor _, modelID := range peer.Models {\n"
        "\t\t\tmodelIDs[modelID] = struct{}{}\n"
        '\t\t\tdata = append(data, newRecord(modelID, peerID+": "+modelID, "", map[string]any{"peerID": peerID}, config.ModelCapConfig{}, "unloaded"))\n'
        "\t\t}\n"
        "\t}\n"
        "\n"
        "\t// Flock-served cloud models (delegated to :8000). The retired in-process\n"
        "\t// astMatrix router used to be the source of these; Flock is now the\n"
        "\t// source of truth, so :25100 discovery must expose its model IDs.\n"
        "\tif s.cloud != nil {\n"
        "\t\tfor alias := range s.cloud.Aliases() {\n"
        "\t\t\tif _, dup := modelIDs[alias]; dup {\n"
        "\t\t\t\tcontinue\n"
        "\t\t\t}\n"
        "\t\t\tmodelIDs[alias] = struct{}{}\n"
        '\t\t\tdata = append(data, newRecord(alias, "flock (alias): "+alias, "", map[string]any{"flock": true, "alias": true}, config.ModelCapConfig{}, "cloud"))\n'
        "\t\t}\n"
        "\t\tfor _, modelID := range s.cloud.ModelIDs() {\n"
        "\t\t\tif _, dup := modelIDs[modelID]; dup {\n"
        "\t\t\t\tcontinue\n"
        "\t\t\t}\n"
        "\t\t\tmodelIDs[modelID] = struct{}{}\n"
        '\t\t\tdata = append(data, newRecord(modelID, "flock: "+modelID, "", map[string]any{"flock": true, "cloud": true}, config.ModelCapConfig{}, "cloud"))\n'
        "\t\t}\n"
        "\t}\n",
    ),
])

print("all patches applied")
