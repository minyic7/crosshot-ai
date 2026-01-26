"""Monitor network requests when applying filters."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_network():
    """Monitor network requests during filter operations."""

    output_dir = Path("data/screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    keyword = "melbourne"
    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    # Store captured requests
    captured_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        # Set up request interception
        async def handle_request(request):
            if "search" in request.url.lower() or "note" in request.url.lower():
                captured_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "post_data": request.post_data
                })

        page.on("request", handle_request)

        url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        print(f"访问: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(6)

        if "captcha" in page.url:
            print("等待扫码...")
            for i in range(60, 0, -5):
                await asyncio.sleep(5)
                if "captcha" not in page.url:
                    break
            await asyncio.sleep(3)

        print("\n初始加载时捕获的请求:")
        for req in captured_requests[-5:]:
            print(f"  {req['method']} {req['url'][:100]}...")
            if req['post_data']:
                print(f"    POST data: {req['post_data'][:200]}...")

        # Clear and open filter panel
        captured_requests.clear()
        print("\n\n打开筛选面板...")

        filter_btn = page.locator("div.filter").first
        await filter_btn.click()
        await asyncio.sleep(2)

        # Click "最新"
        print("\n点击 '最新' 选项...")
        newest = page.locator(".filter-panel >> text=最新").first
        if await newest.count() > 0:
            await newest.click()
            await asyncio.sleep(3)

            print("\n选择'最新'后捕获的请求:")
            for req in captured_requests:
                print(f"\n  {req['method']} {req['url']}")
                if req['post_data']:
                    try:
                        # Parse JSON post data
                        data = json.loads(req['post_data'])
                        print(f"  POST JSON: {json.dumps(data, ensure_ascii=False, indent=4)[:500]}")
                    except:
                        print(f"  POST data: {req['post_data'][:300]}")

        # Screenshot
        await page.screenshot(path=str(output_dir / "network_newest.png"))

        # Clear and try another filter
        captured_requests.clear()

        # Reopen panel
        await page.click("body", position={"x": 500, "y": 500})
        await asyncio.sleep(1)

        filter_btn = page.locator("div.filter").first
        await filter_btn.click()
        await asyncio.sleep(1)

        print("\n\n点击 '最多点赞' 选项...")
        most_liked = page.locator(".filter-panel >> text=最多点赞").first
        if await most_liked.count() > 0:
            await most_liked.click()
            await asyncio.sleep(3)

            print("\n选择'最多点赞'后捕获的请求:")
            for req in captured_requests:
                print(f"\n  {req['method']} {req['url']}")
                if req['post_data']:
                    try:
                        data = json.loads(req['post_data'])
                        print(f"  POST JSON: {json.dumps(data, ensure_ascii=False, indent=4)[:500]}")
                    except:
                        print(f"  POST data: {req['post_data'][:300]}")

        await page.screenshot(path=str(output_dir / "network_most_liked.png"))

        print("\n\n等待10秒...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_network())
