import os,json
from pathlib import Path

P=Path(__file__).parent/'prompts.json'

def load():
    if P.exists():return json.loads(P.read_text())
    return{}

def get(k,**kw):
    d=load()
    t=d.get(k,k)
    return t.format(**kw) if kw else t

def save(d):
    P.write_text(json.dumps(d,indent=2))

def add(k,t):
    d=load();d[k]=t;save(d)

if __name__=='__main__':
    import sys
    if len(sys.argv)>1:print(get(sys.argv[1]))
    else:print(json.dumps(load(),indent=2))
