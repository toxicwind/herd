import os,json,subprocess
from pathlib import Path

def k8s_api(cmd,timeout=3):
    T='/var/run/secrets/kubernetes.io/serviceaccount/token'
    C='/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'
    if not Path(T).exists():return{'e':'no token'}
    tok=Path(T).read_text().strip()
    ns=Path('/var/run/secrets/kubernetes.io/serviceaccount/namespace').read_text().strip()
    api=os.environ.get('KUBERNETES_SERVICE_HOST','192.168.0.1')
    full=f"curl -sk -H 'Authorization: Bearer {tok}' --cacert {C} https://{api}{cmd}"
    try:
        p=subprocess.run(full,shell=True,capture_output=True,text=True,timeout=timeout)
        return{'o':p.stdout,'e':p.stderr,'r':p.returncode}
    except Exception as e:
        return{'e':str(e)}

def nodes():
    r=k8s_api('/api/v1/nodes')
    if r.get('o'):return json.loads(r['o']).get('items',[])
    return[]

def pods(ns=None):
    cmd='/api/v1/pods' if not ns else f'/api/v1/namespaces/{ns}/pods'
    r=k8s_api(cmd)
    if r.get('o'):return json.loads(r['o']).get('items',[])
    return[]

def services(ns=None):
    cmd='/api/v1/services' if not ns else f'/api/v1/namespaces/{ns}/services'
    r=k8s_api(cmd)
    if r.get('o'):return json.loads(r['o']).get('items',[])
    return[]

if __name__=='__main__':
    print('nodes:',len(nodes()))
    print('pods:',len(pods()))
