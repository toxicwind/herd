import subprocess,sys,json,os

def x(c,t=30):
    try: p=subprocess.run(c,shell=True,capture_output=True,text=True,timeout=t); return{'o':p.stdout,'e':p.stderr,'r':p.returncode}
    except Exception as e: return{'e':str(e),'r':-1}

def ck(p):
    r=x(f"{sys.executable} -c 'import {p};print(chr(79)+chr(75))' 2>&1")
    return{'p':p,'ok':'OK' in r['o'],'o':r['o'][:100],'e':r['e'][:100]}

def in2(ps):
    miss=[p for p in ps if not ck(p)['ok']]
    if not miss: return{'s':'all_ok','miss':[]}
    r=x(f"{sys.executable} -m pip install {' '.join(miss)} --user 2>&1",180)
    still=[p for p in miss if not ck(p)['ok']]
    return{'s':'done','miss':still,'r':r['r'],'o':r['o'][:2000]}

def cdp_f(url,t=30):
    r=x(f"python3 /mnt/agents/output/cdp_wrapper.py fetch '{json.dumps({'url':url,'timeout':t*1000})}'",t+5)
    try: d=json.loads(r['o']); return{'ok':d.get('ok'),'c':d.get('content','')[:5000]}
    except: return{'ok':False,'e':r['e'][:200]}

def cdp_e(js,t=30):
    r=x(f"python3 /mnt/agents/output/cdp_wrapper.py eval '{json.dumps({'script':js})}'",t+5)
    try: d=json.loads(r['o']); return{'ok':d.get('ok'),'r':d.get('result'),'e':d.get('error','')}
    except: return{'ok':False,'e':r['e'][:200]}

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='ck':
        print(json.dumps(ck(sys.argv[2])))
    elif len(sys.argv)>1 and sys.argv[1]=='in':
        print(json.dumps(in2(sys.argv[2].split(','))))
    elif len(sys.argv)>1 and sys.argv[1]=='cdp_f':
        print(json.dumps(cdp_f(sys.argv[2])))
    elif len(sys.argv)>1 and sys.argv[1]=='cdp_e':
        print(json.dumps(cdp_e(sys.argv[2])))
    else:
        print(json.dumps({'e':'usage: h.py ck|in|cdp_f|cdp_e <arg>'}))