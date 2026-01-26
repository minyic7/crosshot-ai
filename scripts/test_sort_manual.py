"""Demo script with manual QR code scan."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def demo_with_manual_login():
    """Wait for manual QR scan then test sort."""

    output_dir = Path("data/screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    keyword = "melbourne"
    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    print(f"Loaded {len(cookies)} cookies from .env")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        if cookies:
            await context.add_cookies(cookies)
            print("Cookies added")

        page = await context.new_page()

        url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        print(f"\nNavigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded")

        # Check if we hit captcha
        await asyncio.sleep(3)
        current_url = page.url

        if "captcha" in current_url or "login" in current_url:
            print("\n" + "=" * 60)
            print("请扫描二维码登录...")
            print("你有 60 秒的时间扫码...")
            print("=" * 60)

            # Wait 60 seconds for QR scan
            for i in range(60, 0, -5):
                print(f"剩余 {i} 秒...")
                await asyncio.sleep(5)

                # Check if we left the captcha page
                if "captcha" not in page.url and "login" not in page.url:
                    print("检测到登录成功!")
                    break

            # Wait for page to load after login
            await asyncio.sleep(3)

        # Now test the sort options
        print("\n开始测试排序功能...\n")

        sort_options = [
            ("general", "综合"),
            ("popularity_descending", "最热"),
            ("time_descending", "最新"),
        ]

        for sort_value, sort_name in sort_options:
            url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&sort={sort_value}"

            print(f"\n{'='*60}")
            print(f"排序: {sort_name} ({sort_value})")
            print(f"URL: {url}")
            print(f"{'='*60}")

            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # Take screenshot
            screenshot_path = output_dir / f"sort_{sort_value}.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"截图已保存: {screenshot_path}")

            # Get current URL
            print(f"当前URL: {page.url}")

            # Extract notes
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

            print(f"前5条笔记:")
            for i, n in enumerate(notes, 1):
                print(f"  {i}. {n['title']}... (点赞: {n['likes']})")

        print("\n\n测试完成!")
        print("10秒后关闭浏览器...")
        await asyncio.sleep(10)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(demo_with_manual_login())
