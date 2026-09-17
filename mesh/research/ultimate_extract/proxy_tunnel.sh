#!/bin/bash
# HTTP CONNECT proxy tunnel wrapper
# Usage: proxy_tunnel.sh <target_host> <target_port> <command>

PROXY_HOST="10.86.13.73"
PROXY_PORT="5900"
TARGET_HOST="$1"
TARGET_PORT="$2"
shift 2

# Create tunnel using socat or nc
if command -v socat >/dev/null 2>&1; then
    socat - PROXY-CONNECT:$PROXY_HOST:$PROXY_PORT:$TARGET_HOST:$TARGET_PORT
elif command -v nc >/dev/null 2>&1; then
    # Manual CONNECT tunnel
    {
        echo "CONNECT $TARGET_HOST:$TARGET_PORT HTTP/1.1"
        echo "Host: $TARGET_HOST:$TARGET_PORT"
        echo ""
        sleep 0.5
        cat
    } | nc $PROXY_HOST $PROXY_PORT
else
    echo "No tunneling tool available"
    exit 1
fi
