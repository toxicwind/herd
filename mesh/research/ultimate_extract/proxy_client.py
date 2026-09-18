#!/usr/bin/env python3
"""
HTTP CONNECT Proxy Tunnel Client
================================
Connects through the HTTP CONNECT proxy at 10.86.13.73:5900
to access any internal or external service.
"""

import socket
import sys
import ssl
import json

def proxy_tunnel(target_host, target_port, proxy_host="10.86.13.73", proxy_port=5900):
    """Create a TCP tunnel through the HTTP CONNECT proxy."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        # Connect to proxy
        sock.connect((proxy_host, proxy_port))

        # Send CONNECT request
        connect_req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n"
        sock.sendall(connect_req.encode())

        # Read response
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        response_str = response.decode()
        if "200" not in response_str:
            return None, f"Proxy error: {response_str[:200]}"

        return sock, None

    except Exception as e:
        sock.close()
        return None, str(e)

def http_request(target_host, target_port, method="GET", path="/", headers=None, body=None, use_ssl=False):
    """Make HTTP request through proxy tunnel."""
    sock, error = proxy_tunnel(target_host, target_port)
    if error:
        return {"ok": False, "error": error}

    try:
        if use_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=target_host)

        # Build request
        req_lines = [f"{method} {path} HTTP/1.1", f"Host: {target_host}:{target_port}"]
        if headers:
            for k, v in headers.items():
                req_lines.append(f"{k}: {v}")
        req_lines.append("Connection: close")
        req_lines.append("")

        request = "\r\n".join(req_lines)
        if body:
            request += "\r\n" + body

        sock.sendall(request.encode())

        # Read response
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        sock.close()

        # Parse response
        response_str = response.decode(errors="replace")
        header_end = response_str.find("\r\n\r\n")
        if header_end > 0:
            body = response_str[header_end + 4:]
        else:
            body = response_str

        return {"ok": True, "body": body, "raw": response_str[:500]}

    except Exception as e:
        sock.close()
        return {"ok": False, "error": str(e)}

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: proxy_client.py <host> <port> [path]"}))
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    path = sys.argv[3] if len(sys.argv) > 3 else "/"

    result = http_request(host, port, path=path)
    print(json.dumps(result))

if __name__ == "__main__":
    main()
