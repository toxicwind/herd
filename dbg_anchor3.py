#!/usr/bin/env python3
import ast
s = open("internal/server/server.go").read()
scr = open("patch_herd.py").read()
# Find server.go patch block: locate the Init anchor start in script
i = scr.find('"\\t// Initialize cloud router')
# find the enclosing tuple: walk back to '(\n'
j = scr.rfind("(", 0, i)
# find matching close: the tuple ends with '    ),' at col 4
k = scr.find("\n    ),", i)
tup_src = scr[j:k+1]
tup = ast.literal_eval(tup_src)
old, new = tup
print("old in s:", old in s)
print("old len:", len(old))
# first diff
p = 0
start = s.find(old[:40])
seg = s[start:start+len(old)+10]
for n in range(min(len(old), len(seg))):
    if old[n] != seg[n]:
        print("diff at", n, "script:", repr(old[max(0,n-30):n+30]), "actual:", repr(seg[max(0,n-30):n+30]))
        break
else:
    print("prefix identical; old longer or equal")
