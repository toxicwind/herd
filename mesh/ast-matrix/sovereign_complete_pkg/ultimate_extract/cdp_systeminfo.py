
import asyncio
from playwright.async_api import async_playwright

async def get_system_info():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        # Get browser version info
        version = await browser.new_context()
        page = await version.new_page()
        await page.goto("chrome://version/")
        content = await page.content()
        await browser.close()
        return content

result = asyncio.run(get_system_info())
print(result[:5000])
