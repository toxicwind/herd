
import asyncio
from playwright.async_api import async_playwright

async def test_cdp():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("http://localhost:8888/health")
            content = await page.content()
            print(f"CDP SUCCESS: {content[:200]}")
            await browser.close()
        except Exception as e:
            print(f"CDP ERROR: {e}")

asyncio.run(test_cdp())
