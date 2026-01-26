"""Test different filter options and analyze URL changes."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_options():
    """Test filter options and track URL changes."""

    output_dir = Path("data/screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    keyword = "melbourne"
    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

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

        print(f"\n初始 URL: {page.url}")

        # Open filter panel by clicking
        print("\n打开筛选面板...")
        await page.evaluate("""() => {
            const elements = document.querySelectorAll('*');
            for (const el of elements) {
                const text = el.innerText?.trim();
                if (text === '筛选') {
                    const rect = el.getBoundingClientRect();
                    if (rect.left > 1000) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
        await asyncio.sleep(2)

        # Take screenshot of filter panel
        await page.screenshot(path=str(output_dir / "filter_panel.png"))
        print("截图: 筛选面板")

        # Test different filter options
        filter_tests = [
            ("最新", "sort_newest"),
            ("最多点赞", "sort_most_liked"),
            ("最多收藏", "sort_most_collected"),
            ("一天内", "time_1day"),
            ("一周内", "time_1week"),
        ]

        results = []

        for option_text, test_name in filter_tests:
            print(f"\n{'='*50}")
            print(f"测试选项: {option_text}")
            print(f"{'='*50}")

            # First reset - click 重置
            reset_btn = page.locator("text=重置").first
            if await reset_btn.count() > 0:
                await reset_btn.click()
                await asyncio.sleep(1)

            # Click the option
            option = page.locator(f".filter-panel >> text={option_text}").first
            if await option.count() == 0:
                option = page.locator(f"text={option_text}").first

            if await option.count() > 0:
                await option.click()
                await asyncio.sleep(1)

                # Take screenshot
                await page.screenshot(path=str(output_dir / f"filter_{test_name}.png"))

                # Check current URL
                current_url = page.url
                print(f"URL: {current_url}")

                # Parse URL parameters
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(current_url)
                params = parse_qs(parsed.query)
                print(f"URL 参数: {params}")

                results.append({
                    "option": option_text,
                    "url": current_url,
                    "params": params
                })
            else:
                print(f"未找到选项: {option_text}")

        # Print summary
        print("\n\n" + "="*60)
        print("筛选参数总结")
        print("="*60)

        for r in results:
            print(f"\n{r['option']}:")
            print(f"  参数: {r['params']}")

        # Now test clicking "收起" to close panel and see final URL
        print("\n\n点击'收起'关闭面板...")
        collapse_btn = page.locator("text=收起").first
        if await collapse_btn.count() > 0:
            await collapse_btn.click()
            await asyncio.sleep(2)
            print(f"关闭后 URL: {page.url}")

        # Extract notes with filter applied
        print("\n\n筛选后的笔记:")
        notes = await page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item');
            return Array.from(cards).slice(0, 5).map(card => {
                const titleEl = card.querySelector('.title span');
                const likesEl = card.querySelector('.like-wrapper .count');
                return {
                    title: titleEl ? titleEl.textContent.trim().substring(0, 30) : 'N/A',
                    likes: likesEl ? likesEl.textContent.trim() : '0'
                };
            });
        }""")

        for i, n in enumerate(notes, 1):
            print(f"  {i}. {n['title']}... ({n['likes']})")

        print("\n\n等待10秒后关闭...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_options())
