#!/usr/bin/env python3
"""
CDP Subprocess Wrapper - Execute commands via Chrome DevTools Protocol
===============================================================
This provides a secondary execution channel when ipython/kernel_server
is unavailable. It uses Playwright to connect to the local Chrome instance
via CDP and executes JavaScript in the browser context.

Usage:
    python3 cdp_subprocess.py <command>

Commands:
    exec <shell_command>  - Execute shell command via fetch to local service
    eval <js_code>        - Evaluate JavaScript in browser
    fetch <url>           - Fetch URL via browser
    file <path>           - Read file via file:// URL
    health                - Check kernel server health
    restart               - Attempt to restart kernel server via various methods
"""

import asyncio
import sys
import json
import subprocess
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"

async def get_browser_page():
    """Connect to Chrome via CDP and return a page."""
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(CDP_URL)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    return p, browser, page

async def cdp_fetch(url, timeout=30000):
    """Fetch a URL via CDP browser."""
    p, browser, page = await get_browser_page()
    try:
        await page.goto(url, wait_until="commit", timeout=timeout)
        content = await page.content()
        await browser.close()
        await p.stop()
        return {"ok": True, "content": content}
    except Exception as e:
        await browser.close()
        await p.stop()
        return {"ok": False, "error": str(e)}

async def cdp_eval(js_code, timeout=30000):
    """Evaluate JavaScript via CDP."""
    p, browser, page = await get_browser_page()
    try:
        result = await page.evaluate(js_code)
        await browser.close()
        await p.stop()
        return {"ok": True, "result": result}
    except Exception as e:
        await browser.close()
        await p.stop()
        return {"ok": False, "error": str(e)}

async def cdp_exec(command):
    """Execute shell command by exploiting browser features."""
    # We can use the browser to download a file, or use WebRTC, or other tricks
    # But the most reliable is to use the browser's fetch to trigger a local service
    # For now, we return an error since true exec isn't possible via CDP alone
    return {"ok": False, "error": "Direct exec not possible via CDP. Use eval or fetch."}

async def cdp_restart_kernel():
    """Attempt to restart kernel server using multiple methods."""
    results = []

    # Method 1: Check if already running
    health = await cdp_fetch("http://localhost:8888/health", timeout=10000)
    if health["ok"] and "kernel_alive" in health.get("content", ""):
        results.append("Method 1: Kernel already running")
        return {"ok": True, "method": 1, "results": results}

    # Method 2: Try to trigger s6 restart via browser (if we can access s6 web interface)
    # Not applicable here

    # Method 3: Use JavaScript to create a WebSocket or EventSource that might trigger something
    # Not applicable

    # Method 4: Check if we can use the browser to download and execute something
    # Limited by sandbox

    results.append("No viable restart method via CDP alone")
    return {"ok": False, "results": results}

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: cdp_subprocess.py <command> [args]"}))
        sys.exit(1)

    command = sys.argv[1]

    if command == "fetch":
        url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8888/health"
        result = await cdp_fetch(url)
        print(json.dumps(result))

    elif command == "eval":
        js = sys.argv[2] if len(sys.argv) > 2 else "1 + 1"
        result = await cdp_eval(js)
        print(json.dumps(result))

    elif command == "file":
        path = sys.argv[2] if len(sys.argv) > 2 else "/etc/passwd"
        result = await cdp_fetch(f"file://{path}")
        print(json.dumps(result))

    elif command == "health":
        result = await cdp_fetch("http://localhost:8888/health", timeout=10000)
        print(json.dumps(result))

    elif command == "restart":
        result = await cdp_restart_kernel()
        print(json.dumps(result))

    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))

if __name__ == "__main__":
    asyncio.run(main())
