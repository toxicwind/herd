#!/usr/bin/env python3
"""Robust line/marker-based patch for internal/server/server.go."""
import sys

p = "internal/server/server.go"
s = open(p).read()
orig = s

# 1. Drop the astmatrix import.
lines = s.split("\n")
lines = [L for L in lines if "mostlygeek/llama-swap/internal/astmatrix" not in L]
s = "\n".join(lines)

# 2. Cloud field type.
old = "\tcloud *astmatrix.Router // cloud model routing via AST Matrix"
assert old in s, "field anchor"
s = s.replace(old, "\tcloud *flockCloud // cloud model routing via Flock delegation (:8000)", 1)

# 3. Replace the init block: from the marker comment to just before "if st == nil".
start_m = "\t// Initialize cloud router (AST Matrix) if configured."
end_m = "\n\tif st == nil {"
i = s.find(start_m)
j = s.find(end_m, i)
assert i != -1 and j != -1, "init block bounds"
new_init = (
    "\t// Initialize cloud delegation (Flock) if configured. The in-process\n"
    "\t// astmatrix.Router was retired 2026-09-17; Flock (:8000) is the unified\n"
    "\t// multi-provider remote-API/completions subsystem behind :25100.\n"
    "\tvar cloud *flockCloud\n"
    "\tif cfg.Flock != nil {\n"
    "\t\tcfg.Flock.Defaults()\n"
    "\t}\n"
    "\tif cfg.Flock != nil && cfg.Flock.Enabled {\n"
    "\t\tcloud = newFlockCloud(cfg.Flock, proxylog)\n"
    '\t\tproxylog.Infof("flock cloud delegation enabled: base=%s aliases=%d", cfg.Flock.BaseURL, len(cfg.Flock.ModelMap))\n'
    "\t}\n"
    "\tif cfg.AstMatrix != nil && cfg.AstMatrix.Enabled {\n"
    '\t\tproxylog.Warnf("astMatrix config block is retired and ignored; configure flock: instead")\n'
    "\t}"
)
s = s[:i] + new_init + s[j:]

# 4. Dispatch log line.
old = 's.proxylog.Debugf("dispatch: using cloud matrix for model: %s", data.ModelID)'
assert old in s, "dispatch anchor"
s = s.replace(old, 's.proxylog.Debugf("dispatch: using flock cloud delegation for model: %s", data.ModelID)', 1)

# 5. Drop the astmatrix health-DB close block (brace-counted).
start_m = "\t// Close the cloud router's health database."
i = s.find(start_m)
assert i != -1, "close anchor"
# find the "if s.cloud != nil {" line, then its matching closing brace
k = s.find("if s.cloud != nil {", i)
assert k != -1
depth = 0
n = s.find("{", k)
depth = 1
n += 1
while depth > 0:
    c = s[n]
    if c == "{":
        depth += 1
    elif c == "}":
        depth -= 1
    n += 1
# n now points just past the matching "}"; also swallow the trailing newline
if s[n:n+1] == "\n":
    n += 1
replacement = "\t// flockCloud holds no provider state to close; Flock owns health/circuits.\n"
s = s[:i] + replacement + s[n:]

assert s != orig
open(p, "w").write(s)
print("server.go patched OK")
