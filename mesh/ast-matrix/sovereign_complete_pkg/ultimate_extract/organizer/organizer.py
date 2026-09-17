import os,json
from pathlib import Path
from collections import defaultdict

R=["00-core","01-kin","02-domain","03-archive","04-quarantine"]

def ring(a):
    return R[a] if 0<=a<len(R) else R[-1]

def organize(analyses,src,tgt):
    tgt=Path(tgt)
    tgt.mkdir(parents=True,exist_ok=True)
    m=[]
    for a in analyses:
        d=tgt/ring(a.get('ring',4))/a.get('lang','unknown')/a.get('domain','misc')
        d.mkdir(parents=True,exist_ok=True)
        s=Path(a['path'])
        if s.exists():
            import shutil
            shutil.copy2(s,d/s.name)
            m.append({'src':str(s),'dst':str(d/s.name),'ring':ring(a.get('ring',4))})
    with open(tgt/'.manifest.json','w') as f:
        json.dump(m,f,indent=2)
    return m

if __name__=='__main__':
    import sys
    analyses=json.load(open(sys.argv[1])) if len(sys.argv)>1 else []
    print(json.dumps(organize(analyses,'.',sys.argv[2] if len(sys.argv)>2 else './organized'),indent=2))
