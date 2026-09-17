import os,time,json

def cpu():
    with open('/proc/stat') as f:
        l=f.readline().split()
    return{'user':int(l[1]),'sys':int(l[3]),'idle':int(l[4])}

def mem():
    d={}
    with open('/proc/meminfo') as f:
        for l in f:
            if ':' in l:
                k,v=l.split(':',1)
                d[k.strip()]=v.strip()
    return d

def load():
    return os.getloadavg()

def snapshot():
    return{'time':time.time(),'cpu':cpu(),'mem':mem(),'load':load()}

if __name__=='__main__':
    print(json.dumps(snapshot(),indent=2))
