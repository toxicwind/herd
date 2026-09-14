#!/usr/bin/env python3
import subprocess,sys,json,os

def x(c,t=30):
    try: p=subprocess.run(c,shell=True,capture_output=True,text=True,timeout=t); return{'o':p.stdout,'e':p.stderr,'r':p.returncode}
    except Exception as e: return{'e':str(e),'r':-1}

def cdp_fetch(url,t=30):
    r=x(f"python3 /mnt/agents/output/cdp_wrapper.py fetch '{json.dumps({'url':url,'timeout':t*1000})}'",t+5)
    try: d=json.loads(r['o']); return{'ok':d.get('ok'),'c':d.get('content','')[:5000],'e':d.get('error','')}
    except: return{'ok':False,'e':r['e'][:200]}

def cdp_eval(js,t=30):
    r=x(f"python3 /mnt/agents/output/cdp_wrapper.py eval '{json.dumps({'script':js})}'",t+5)
    try: d=json.loads(r['o']); return{'ok':d.get('ok'),'r':d.get('result'),'e':d.get('error','')}
    except: return{'ok':False,'e':r['e'][:200]}

def pip_via_cdp(pkg):
    # Use CDP to fetch package from PyPI and install
    url=f"https://pypi.org/pypi/{pkg}/json"
    r=cdp_fetch(url)
    if not r['ok']: return{'ok':False,'e':r['e']}
    try:
        d=json.loads(r['c'])
        v=d['info']['version']
        whl=d['urls'][0]['url'] if d['urls'] else None
        return{'ok':True,'pkg':pkg,'ver':v,'whl':whl}
    except Exception as e:
        return{'ok':False,'e':str(e)}

if __name__=='__main__':
    if len(sys.argv)>1:
        print(json.dumps(pip_via_cdp(sys.argv[1])))
    else:
        print(json.dumps({'e':'Usage: cdp_pip.py <package>'}))
