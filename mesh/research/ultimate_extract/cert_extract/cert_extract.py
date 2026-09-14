import socket,ssl

def get_cert(h,p=443,t=1):
    ctx=ssl.create_default_context()
    ctx.check_hostname=False
    ctx.verify_mode=ssl.CERT_NONE
    try:
        with socket.create_connection((h,p),timeout=t) as s:
            with ctx.wrap_socket(s,server_hostname=h) as ss:
                c=ss.getpeercert()
                return{
                    'subject':c.get('subject'),
                    'issuer':c.get('issuer'),
                    'not_after':c.get('notAfter'),
                    'san':c.get('subjectAltName'),
                    'serial':c.get('serialNumber')
                }
    except Exception as e:
        return{'e':str(e)}

if __name__=='__main__':
    import json,sys
    h=sys.argv[1] if len(sys.argv)>1 else 'localhost'
    p=int(sys.argv[2]) if len(sys.argv)>2 else 443
    print(json.dumps(get_cert(h,p),indent=2))
