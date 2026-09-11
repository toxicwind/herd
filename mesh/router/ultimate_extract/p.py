#!/usr/bin/env python3
import subprocess,sys,json
def r(c,t=30):
    try: p=subprocess.run(c,shell=True,capture_output=True,text=True,timeout=t); return {'o':p.stdout,'e':p.stderr,'r':p.returncode}
    except Exception as e: return {'e':str(e),'r':-1}

def i(p):
    x=r(f"{sys.executable} -m pip install {p} 2>&1")
    return {'p':p,'o':x['o'][:500],'e':x['e'][:500],'r':x['r']}

def c(p):
    x=r(f"{sys.executable} -c 'import {p};print("OK")' 2>&1")
    return {'p':p,'s':x['o'].strip()=='OK','o':x['o'][:200],'e':x['e'][:200]}

if __name__=='__main__':
    pkgs=['nltk','textblob','vaderSentiment','sklearn','numpy','pandas','matplotlib','seaborn','transformers','torch','spacy','requests','flask','fastapi','uvicorn','playwright','selenium','beautifulsoup4','lxml','jupyter','ipython']
    print(json.dumps({'installed':[p for p in pkgs if c(p)['s']],'missing':[p for p in pkgs if not c(p)['s']]}))
