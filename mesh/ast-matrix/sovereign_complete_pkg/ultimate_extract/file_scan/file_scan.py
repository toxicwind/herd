import os,hashlib,json
from pathlib import Path
from collections import defaultdict

def hash_file(p,bs=65536):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        while True:
            c=f.read(bs)
            if not c:break
            h.update(c)
    return h.hexdigest()

def scan(d,exts=None,min_sz=0):
    d=Path(d)
    r=[]
    for p in d.rglob('*'):
        if not p.is_file():continue
        sz=p.stat().st_size
        if sz<min_sz:continue
        if exts and p.suffix not in exts:continue
        r.append({'path':str(p),'size':sz,'ext':p.suffix})
    return r

def dupes(d,exts=None):
    d=Path(d)
    h=defaultdict(list)
    for p in d.rglob('*'):
        if not p.is_file():continue
        if exts and p.suffix not in exts:continue
        try:
            fh=hash_file(p)
            h[fh].append(str(p))
        except:
            pass
    return {k:v for k,v in h.items() if len(v)>1}

if __name__=='__main__':
    import sys
    d=sys.argv[1] if len(sys.argv)>1 else '.'
    print(json.dumps(dupes(d),indent=2))
