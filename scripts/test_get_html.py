"""Get HTML of XHS search page for analysis."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def get_html():
    """Save page HTML for analysis."""

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
        print(f"Loading: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(8)  # Wait longer

        # Take screenshot
        await page.screenshot(path="data/screenshots/inspect_page.png")
        print("Screenshot saved")

        # Get the filter row HTML specifically
        filter_html = await page.evaluate("""() => {
            // Find elements containing filter keywords
            const body = document.body.innerHTML;

            // Look for any element containing these filter words
            const filterWords = ['筛选', '综合', '最新', '视频', '图文'];
            const results = [];

            document.querySelectorAll('*').forEach(el => {
                const text = el.innerText || el.textContent || '';
                if (filterWords.some(w => text.includes(w)) && text.length < 100) {
                    results.push({
                        tag: el.tagName,
                        class: el.className,
                        text: text.substring(0, 80),
                        html: el.outerHTML.substring(0, 200)
                    });
                }
            });

            return results.slice(0, 20);
        }""")

        print("\nElements with filter keywords:")
        for i, f in enumerate(filter_html[:15]):
            print(f"\n{i+1}. [{f['tag']}] class='{f['class']}'")
            print(f"   text: {f['text'][:60]}")

        # Get URL parameters
        print(f"\nCurrent URL: {page.url}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(get_html())
