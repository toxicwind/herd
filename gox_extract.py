#!/usr/bin/env python3
"""Manually extract Go module zips from the download cache.

The local go toolchain's extraction produces empty dirs; this replicates the
layout: <GOMODCACHE>/<escaped-module>@<version>/ with files read-only.
"""
import os
import sys
import zipfile

CACHE = "/home/toxic/go/pkg/mod/cache/download"
DEST = "/home/toxic/go/pkg/mod"

def unescape(p):
    out = []
    i = 0
    while i < len(p):
        if p[i] == "!" and i + 1 < len(p):
            out.append(p[i+1].upper())
            i += 2
        else:
            out.append(p[i])
            i += 1
    return "".join(out)

count = 0
for root, dirs, files in os.walk(CACHE):
    for fn in files:
        if not fn.endswith(".zip"):
            continue
        # root = CACHE/<escaped-mod-path>/@v ; fn = <version>.zip
        rel = os.path.relpath(root, CACHE)
        parts = rel.split(os.sep)
        if parts[-1] != "@v":
            continue
        esc_mod = os.sep.join(parts[:-1])
        version = fn[:-4]
        mod = unescape(esc_mod.replace(os.sep, "/"))
        prefix = mod + "@" + version + "/"
        target = os.path.join(DEST, esc_mod + "@" + version)
        if os.path.isdir(target):
            for r, ds, fs in os.walk(target):
                os.chmod(r, 0o755)
        zpath = os.path.join(root, fn)
        try:
            with zipfile.ZipFile(zpath) as z:
                for info in z.infolist():
                    name = info.filename
                    if not name.startswith(prefix):
                        continue
                    relname = name[len(prefix):]
                    if not relname:
                        continue
                    dest = os.path.join(target, relname)
                    if info.is_dir():
                        os.makedirs(dest, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with z.open(info) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
            # read-only perms like the go tool
            for r, ds, fs in os.walk(target):
                for d in ds:
                    os.chmod(os.path.join(r, d), 0o555)
                for f in fs:
                    os.chmod(os.path.join(r, f), 0o444)
            os.chmod(target, 0o555)
            count += 1
        except Exception as e:
            print(f"FAIL {zpath}: {e}", file=sys.stderr)
print(f"extracted {count} modules")
