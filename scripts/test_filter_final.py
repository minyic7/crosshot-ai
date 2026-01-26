"""Final test for filter options with hover to keep panel open."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_final():
    """Test filter with hover approach."""

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

        print(f"\n初始 URL: {page.url}\n")

        # Helper to extract notes
        async def get_notes():
            return await page.evaluate("""() => {
                const cards = document.querySelectorAll('section.note-item');
                return Array.from(cards).slice(0, 5).map(card => {
                    const titleEl = card.querySelector('.title span');
                    const likesEl = card.querySelector('.like-wrapper .count');
                    return {
                        title: titleEl ? titleEl.textContent.trim().substring(0, 25) : 'N/A',
                        likes: likesEl ? likesEl.textContent.trim() : '0'
                    };
                });
            }""")

        # Get initial notes
        print("默认排序 (综合) 的前5条笔记:")
        initial_notes = await get_notes()
        for i, n in enumerate(initial_notes, 1):
            print(f"  {i}. {n['title']}... ({n['likes']})")

        # Test different filters
        filter_tests = [
            ("排序依据", "最新", "newest"),
            ("排序依据", "最多点赞", "most_liked"),
            ("发布时间", "一天内", "time_1day"),
        ]

        for category, option, name in filter_tests:
            print(f"\n{'='*60}")
            print(f"测试: {category} -> {option}")
            print(f"{'='*60}")

            # Open filter panel
            filter_btn = page.locator("text=筛选").last  # 右上角的筛选
            await filter_btn.click()
            await asyncio.sleep(1)

            # Find and click the option within the filter panel
            # The panel has class 'filter-panel'
            panel = page.locator(".filter-panel")

            if await panel.count() > 0:
                # Click the specific option
                option_btn = panel.locator(f"text={option}").first
                if await option_btn.count() > 0:
                    await option_btn.click()
                    await asyncio.sleep(2)

                    # Take screenshot
                    await page.screenshot(path=str(output_dir / f"final_{name}.png"))

                    # Get URL
                    print(f"URL: {page.url}")

                    # Parse params
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(page.url)
                    params = parse_qs(parsed.query)
                    print(f"参数: {params}")

                    # Get notes
                    notes = await get_notes()
                    print(f"\n前5条笔记:")
                    for i, n in enumerate(notes, 1):
                        print(f"  {i}. {n['title']}... ({n['likes']})")

                    # Click outside to close panel or click 重置
                    reset_btn = panel.locator("text=重置").first
                    if await reset_btn.count() > 0:
                        await reset_btn.click()
                        await asyncio.sleep(1)

                    # Close panel by clicking elsewhere
                    await page.click("body", position={"x": 500, "y": 500})
                    await asyncio.sleep(1)
                else:
                    print(f"未找到选项: {option}")
            else:
                print("筛选面板未打开")

        print("\n\n测试完成！等待10秒...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_final())
