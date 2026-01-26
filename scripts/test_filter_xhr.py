"""Monitor XHR requests when applying filters."""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_xhr():
    """Monitor all XHR requests during filter operations."""

    output_dir = Path("data/screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    keyword = "melbourne"
    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    # Store captured requests
    xhr_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        # Intercept ALL requests
        async def handle_request(request):
            # Only capture XHR/Fetch requests
            if request.resource_type in ["xhr", "fetch"]:
                xhr_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "post_data": request.post_data,
                    "headers": dict(request.headers)
                })

        page.on("request", handle_request)

        url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        print(f"访问: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(8)

        if "captcha" in page.url:
            print("等待扫码...")
            for i in range(60, 0, -5):
                await asyncio.sleep(5)
                if "captcha" not in page.url:
                    break
            await asyncio.sleep(3)

        print(f"\n初始加载捕获了 {len(xhr_requests)} 个XHR请求")
        print("\n关键API请求:")
        for req in xhr_requests:
            parsed = urlparse(req['url'])
            if 'search' in parsed.path.lower() or 'note' in parsed.path.lower() or 'feed' in parsed.path.lower():
                print(f"\n  {req['method']} {parsed.path}")
                print(f"  Query: {parse_qs(parsed.query)}")
                if req['post_data']:
                    print(f"  Body: {req['post_data'][:300]}")

        # Clear and test filter
        xhr_requests.clear()
        print("\n\n" + "="*60)
        print("打开筛选面板并点击'最新'")
        print("="*60)

        filter_btn = page.locator("div.filter").first
        await filter_btn.click()
        await asyncio.sleep(1)

        newest = page.locator(".filter-panel >> text=最新").first
        if await newest.count() > 0:
            await newest.click()
            await asyncio.sleep(4)

        print(f"\n选择'最新'后捕获了 {len(xhr_requests)} 个XHR请求")
        for req in xhr_requests:
            parsed = urlparse(req['url'])
            print(f"\n  {req['method']} {parsed.path}")
            print(f"  Full URL: {req['url'][:150]}")
            qs = parse_qs(parsed.query)
            if qs:
                print(f"  Query params: {qs}")
            if req['post_data']:
                try:
                    data = json.loads(req['post_data'])
                    print(f"  Body (JSON): {json.dumps(data, ensure_ascii=False)[:400]}")
                except:
                    print(f"  Body: {req['post_data'][:300]}")

        # Take screenshot
        await page.screenshot(path=str(output_dir / "xhr_newest.png"))

        # Test another filter
        xhr_requests.clear()
        print("\n\n" + "="*60)
        print("点击'最多点赞'")
        print("="*60)

        # Close and reopen panel
        await page.click("body", position={"x": 500, "y": 500})
        await asyncio.sleep(1)

        filter_btn = page.locator("div.filter").first
        await filter_btn.click()
        await asyncio.sleep(1)

        most_liked = page.locator(".filter-panel >> text=最多点赞").first
        if await most_liked.count() > 0:
            await most_liked.click()
            await asyncio.sleep(4)

        print(f"\n选择'最多点赞'后捕获了 {len(xhr_requests)} 个XHR请求")
        for req in xhr_requests:
            parsed = urlparse(req['url'])
            print(f"\n  {req['method']} {parsed.path}")
            print(f"  Full URL: {req['url'][:150]}")
            qs = parse_qs(parsed.query)
            if qs:
                print(f"  Query params: {qs}")
            if req['post_data']:
                try:
                    data = json.loads(req['post_data'])
                    print(f"  Body (JSON): {json.dumps(data, ensure_ascii=False)[:400]}")
                except:
                    print(f"  Body: {req['post_data'][:300]}")

        await page.screenshot(path=str(output_dir / "xhr_most_liked.png"))

        print("\n\n等待10秒...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_xhr())
