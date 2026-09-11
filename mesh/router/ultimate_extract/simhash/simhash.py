import hashlib,struct
from collections import Counter

def _hash(s):
    return struct.unpack('>Q',hashlib.sha256(s.encode()).digest()[:8])[0]

def f(v,n=64):
    r=[0]*n
    for i in range(n):
        r[i]=1 if(v>>i)&1 else -1
    return r

def simhash(t,n=64):
    c=Counter()
    for w in t.split():
        c[w]+=1
    v=[0]*n
    for w,ct in c.items():
        h=_hash(w)
        for i in range(n):
            v[i]+=ct if(h>>i)&1 else -ct
    r=0
    for i in range(n):
        if v[i]>0:r|=(1<<i)
    return r

def dist(a,b):
    return bin(a^b).count('1')

def near(a,b,th=3):
    return dist(a,b)<=th

if __name__=='__main__':
    import sys
    a=simhash(sys.argv[1] if len(sys.argv)>1 else 'hello world')
    b=simhash(sys.argv[2] if len(sys.argv)>2 else 'hello there')
    print(f'dist={dist(a,b)} near={near(a,b)}')
