
import asyncio
import sys
import json
from playwright.async_api import async_playwright

async def cdp_execute(command_type, payload):
    """Execute commands via Chrome DevTools Protocol."""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()

            if command_type == "fetch":
                # Use CDP to fetch a URL
                await page.goto(payload["url"], wait_until="networkidle", timeout=payload.get("timeout", 30000))
                content = await page.content()
                result = {"ok": True, "content": content[:10000], "url": payload["url"]}

            elif command_type == "eval":
                # Execute JavaScript in browser context
                result_obj = await page.evaluate(payload["script"])
                result = {"ok": True, "result": result_obj}

            elif command_type == "screenshot":
                # Take screenshot
                await page.goto(payload["url"], wait_until="networkidle")
                screenshot = await page.screenshot(full_page=True, type="png")
                with open(payload.get("output", "/mnt/agents/output/screenshot.png"), "wb") as f:
                    f.write(screenshot)
                result = {"ok": True, "output": payload.get("output", "/mnt/agents/output/screenshot.png")}

            elif command_type == "xhr":
                # Use XMLHttpRequest for more control
                script = """
                async () => {
                    const response = await fetch("%s", {
                        method: "%s",
                        headers: %s,
                        body: %s
                    });
                    const text = await response.text();
                    return {status: response.status, text: text.substring(0, 5000)};
                }
                """ % (payload["url"], payload.get("method", "GET"), json.dumps(payload.get("headers", {})), json.dumps(payload.get("body")))
                result_obj = await page.evaluate(script)
                result = {"ok": True, "result": result_obj}

            elif command_type == "websocket":
                # Connect to WebSocket via CDP
                script = """
                async () => {
                    return new Promise((resolve, reject) => {
                        const ws = new WebSocket("%s");
                        ws.onopen = () => {
                            ws.send("%s");
                            setTimeout(() => {
                                ws.close();
                                resolve("sent");
                            }, 1000);
                        };
                        ws.onerror = (e) => resolve("error: " + e.message);
                    });
                }
                """ % (payload["url"], payload.get("message", ""))
                result_obj = await page.evaluate(script)
                result = {"ok": True, "result": result_obj}

            await browser.close()
            return result

        except Exception as e:
            return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: cdp_wrapper.py <command_type> <json_payload>"}))
        sys.exit(1)

    command_type = sys.argv[1]
    payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

    result = asyncio.run(cdp_execute(command_type, payload))
    print(json.dumps(result))
