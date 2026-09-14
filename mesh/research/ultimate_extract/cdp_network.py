
import asyncio
from playwright.async_api import async_playwright

async def monitor_network():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        # Listen for all network requests
        requests = []
        def handle_request(request):
            url = request.url
            if any(x in url for x in ['api', 'completion', 'chat', 'kimi', 'openrouter', 'llm']):
                requests.append(url)

        page.on("request", handle_request)

        # Navigate to a page that triggers API calls
        await page.goto("https://kimi.com")
        await asyncio.sleep(3)

        await browser.close()
        return requests

result = asyncio.run(monitor_network())
print(json.dumps(result))
