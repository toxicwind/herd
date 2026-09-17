import subprocess,json,time

def procs():
    r=subprocess.run(['ps','aux'],capture_output=True,text=True)
    lines=r.stdout.strip().split('
')[1:]
    out=[]
    for l in lines:
        p=l.split()
        if len(p)>10:
            out.append({'user':p[0],'pid':p[1],'cpu':p[2],'mem':p[3],'cmd':' '.join(p[10:])})
    return out

def top_cpu(n=10):
    return sorted(procs(),key=lambda x:float(x['cpu']),reverse=True)[:n]

def find_pid(name):
    return [p for p in procs() if name in p['cmd']]

if __name__=='__main__':
    print(json.dumps(top_cpu(),indent=2))
