"""Demo script to verify XHS search sort functionality with screenshots."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright

from apps.config import get_settings


async def demo_sort_options():
    """Take screenshots of XHS search with different sort options."""

    output_dir = Path("data/screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    keyword = "melbourne"
    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    print(f"Loaded {len(cookies)} cookies from .env")

    # Sort options matching our SortBy enum
    sort_options = {
        "general": "综合 (Default)",
        "popularity_descending": "最热 (Hot)",
        "time_descending": "最新 (Time)",
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False to see the browser
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        # Add cookies from config
        if cookies:
            await context.add_cookies(cookies)
            print("Cookies added to browser context")
        page = await context.new_page()

        for sort_value, sort_name in sort_options.items():
            url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&sort={sort_value}"

            print(f"\n{'='*60}")
            print(f"Sort: {sort_name}")
            print(f"URL: {url}")
            print(f"{'='*60}")

            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(6)  # Wait for content to load

            # Take screenshot
            screenshot_path = output_dir / f"search_sort_{sort_value}.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            print(f"Screenshot saved: {screenshot_path}")

            # Get current URL to verify sort parameter
            current_url = page.url
            print(f"Current URL: {current_url}")

            # Extract first 3 note titles to compare results
            first_notes = await page.evaluate("""() => {
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
            print(f"First 5 notes:")
            for i, note in enumerate(first_notes, 1):
                print(f"  {i}. {note['title']}... (likes: {note['likes']})")

            await asyncio.sleep(2)

        await browser.close()

    print(f"\n\nScreenshots saved to: {output_dir.absolute()}")


if __name__ == "__main__":
    asyncio.run(demo_sort_options())
