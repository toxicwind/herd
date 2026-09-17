import socket,subprocess,concurrent.futures,time

def ping(h,t=.5):
    try:
        p=subprocess.run(['ping','-c1','-W',str(t),h],capture_output=True,text=True,timeout=t+1)
        return p.returncode==0
    except:
        return False

def port(h,p,t=.5):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.settimeout(t)
    try:
        s.connect((h,p))
        s.close()
        return True
    except:
        return False

def sweep(subnet,ports=None,workers=50):
    if ports is None:ports=[22,80,443,8080,8443]
    hosts=[f"{subnet}.{i}" for i in range(1,255)]
    alive=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        f={ex.submit(ping,h):h for h in hosts}
        for fu in concurrent.futures.as_completed(f):
            if fu.result():
                alive.append(f[fu])
    open_ports=[]
    for h in alive[:20]:
        for p in ports:
            if port(h,p):
                open_ports.append((h,p))
    return{'alive':alive,'ports':open_ports}

if __name__=='__main__':
    import sys
    subnet=sys.argv[1] if len(sys.argv)>1 else '192.168.0'
    print(json.dumps(sweep(subnet),indent=2))
