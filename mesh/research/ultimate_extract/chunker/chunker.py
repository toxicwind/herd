import re

def chunk(t,sz=4000,ov=200):
    if len(t)<=sz:return[t]
    r=[]
    i=0
    while i<len(t):
        r.append(t[i:i+sz])
        i+=sz-ov
    return r

def overlap(a,b):
    mx=min(len(a),len(b),1000)
    for l in range(mx,0,-1):
        if a[-l:]==b[:l]:return l
    return 0

if __name__=='__main__':
    import sys
    t=sys.argv[1] if len(sys.argv)>1 else 'a'*10000
    c=chunk(t)
    print(f'chunks={len(c)} len={[len(x) for x in c]}')
