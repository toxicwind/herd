
import asyncio
from playwright.async_api import async_playwright

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        urls = []
        def handle(req):
            url = req.url
            if 'api' in url or 'chat' in url or 'completion' in url or 'kimi' in url:
                urls.append(url)
        page.on("request", handle)

        # Navigate to kimi.com to trigger API calls
        await page.goto("https://kimi.com", wait_until="networkidle")
        await asyncio.sleep(5)

        await browser.close()
        return urls[:20]

result = asyncio.run(capture())
print(json.dumps(result))
