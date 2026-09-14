import os,sys,subprocess,socket,ssl,time
from pathlib import Path

def R(c,t=3):
    try:
        p=subprocess.run(c,shell=True,capture_output=True,text=True,timeout=t)
        return{'o':p.stdout,'e':p.stderr,'r':p.returncode}
    except Exception as e:
        return{'o':'','e':str(e),'r':-1}

def S(h,p,t=.5):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.settimeout(t)
    try:
        s.connect((h,p))
        s.close()
        return True
    except:
        return False

def recon(out_dir='/tmp/recon'):
    Path(out_dir).mkdir(parents=True,exist_ok=True)
    r=[]
    r.append(('id',R('id')))
    r.append(('caps',R('cat /proc/self/status | grep -E Cap')))
    r.append(('route',R('ip route')))
    r.append(('hosts',R('cat /etc/hosts')))
    r.append(('resolv',R('cat /etc/resolv.conf')))
    for p in [8888,8443,5900,6901,22,80,443,8080,10250,6443]:
        r.append((f'port_{p}',S('127.0.0.1',p)))
    with open(f'{out_dir}/recon.json','w') as f:
        json.dump(r,f,default=str)
    return r

if __name__=='__main__':
    print(json.dumps(recon(),default=str,indent=2))
