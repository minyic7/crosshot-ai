"""Demo script to verify XHS search sort by clicking filter tabs."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def demo_sort_by_click():
    """Take screenshots by clicking different sort tabs."""

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
            print("Cookies added to browser context")

        page = await context.new_page()

        # Go to search page first
        url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        print(f"\nNavigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # Find all filter tabs - they appear as a horizontal row of clickable items
        filter_tabs = await page.evaluate("""() => {
            // The filter row is visible at the top - look for clickable items
            const items = [];

            // Method 1: Find items with specific text
            const allElements = document.querySelectorAll('*');
            const keywords = ['综合', '最新发布', '上三日', '收录最多', '点赞最多'];

            for (const el of allElements) {
                const text = el.textContent?.trim();
                if (text && keywords.includes(text) && el.children.length === 0) {
                    items.push({
                        text: text,
                        tagName: el.tagName,
                        className: el.className
                    });
                }
            }

            return items;
        }""")

        print(f"\nFound filter tabs: {filter_tabs}")

        # Take initial screenshot
        await page.screenshot(path=str(output_dir / "sort_1_initial.png"))
        print("Screenshot 1: Initial page")

        # Helper to extract notes
        async def extract_notes():
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

        # Click different sort options
        sort_tests = [
            ("最新发布", "sort_2_newest.png"),
            ("收录最多", "sort_3_most_collected.png"),
            ("点赞最多", "sort_4_most_likes.png"),
        ]

        for tab_text, filename in sort_tests:
            try:
                print(f"\n--- Trying to click '{tab_text}' ---")
                tab = page.locator(f"text={tab_text}").first
                count = await tab.count()
                print(f"Found {count} element(s) with text '{tab_text}'")

                if count > 0:
                    await tab.click()
                    await asyncio.sleep(4)
                    await page.screenshot(path=str(output_dir / filename))
                    print(f"Screenshot saved: {filename}")

                    current_url = page.url
                    print(f"URL: {current_url}")

                    notes = await extract_notes()
                    print(f"First 5 notes after '{tab_text}':")
                    for i, n in enumerate(notes, 1):
                        print(f"  {i}. {n['title']}... ({n['likes']})")
            except Exception as e:
                print(f"Error clicking '{tab_text}': {e}")

        await browser.close()

    print(f"\n\nScreenshots saved to: {output_dir.absolute()}")


if __name__ == "__main__":
    asyncio.run(demo_sort_by_click())
