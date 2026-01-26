"""Test sort by clicking filter tabs."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_click_sort():
    """Test clicking sort tabs."""

    output_dir = Path("data/screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    keyword = "melbourne"
    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    print(f"Loaded {len(cookies)} cookies")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        # Go to search page
        url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        print(f"\n访问: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(6)

        # Check for captcha
        if "captcha" in page.url:
            print("\n检测到验证码，等待60秒扫码...")
            for i in range(60, 0, -5):
                print(f"  剩余 {i} 秒...")
                await asyncio.sleep(5)
                if "captcha" not in page.url:
                    print("  登录成功!")
                    break
            await asyncio.sleep(3)

        # Take initial screenshot
        await page.screenshot(path=str(output_dir / "click_1_initial.png"))
        print("\n截图1: 初始页面 (综合)")

        # Extract and print first 3 notes
        async def print_notes(label):
            notes = await page.evaluate("""() => {
                const cards = document.querySelectorAll('section.note-item');
                return Array.from(cards).slice(0, 3).map(card => {
                    const titleEl = card.querySelector('.title span');
                    const likesEl = card.querySelector('.like-wrapper .count');
                    return {
                        title: titleEl ? titleEl.textContent.trim().substring(0, 25) : 'N/A',
                        likes: likesEl ? likesEl.textContent.trim() : '0'
                    };
                });
            }""")
            print(f"\n{label} - 前3条笔记:")
            for i, n in enumerate(notes, 1):
                print(f"  {i}. {n['title']}... ({n['likes']})")

        await print_notes("综合")

        # Test clicking different tabs
        tabs_to_test = [
            ("最新发布", "click_2_newest.png"),
            ("收录最多", "click_3_most_collected.png"),
            ("点赞最多", "click_4_most_liked.png"),
        ]

        for tab_text, filename in tabs_to_test:
            print(f"\n{'='*50}")
            print(f"点击: {tab_text}")
            print(f"{'='*50}")

            try:
                tab = page.locator(f"text={tab_text}").first
                count = await tab.count()

                if count > 0:
                    await tab.click()
                    await asyncio.sleep(4)

                    await page.screenshot(path=str(output_dir / filename))
                    print(f"截图已保存: {filename}")

                    await print_notes(tab_text)
                else:
                    print(f"未找到 '{tab_text}' 标签")
            except Exception as e:
                print(f"点击 '{tab_text}' 失败: {e}")

        print("\n\n测试完成! 10秒后关闭浏览器...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_click_sort())
