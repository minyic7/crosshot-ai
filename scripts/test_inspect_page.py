"""Inspect XHS search page to find filter elements."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def inspect_page():
    """Inspect page to find filter elements."""

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
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # Get all unique text content from top area
        texts = await page.evaluate("""() => {
            const results = [];

            // Get all elements in the top 300px of the page
            const elements = document.querySelectorAll('*');
            for (const el of elements) {
                const rect = el.getBoundingClientRect();
                if (rect.top < 150 && rect.top > 50) {
                    const text = el.textContent?.trim();
                    if (text && text.length < 30 && !results.includes(text)) {
                        results.push({
                            text: text,
                            tag: el.tagName,
                            class: el.className?.substring(0, 50),
                            top: Math.round(rect.top)
                        });
                    }
                }
            }
            return results;
        }""")

        print("Elements in top area of page:")
        for t in texts[:30]:
            print(f"  [{t['tag']}] {t['text'][:40]} (class: {t['class'][:30] if t['class'] else 'none'})")

        # Also check what's clickable
        print("\n\nLooking for clickable filter-like elements...")
        clickables = await page.evaluate("""() => {
            const results = [];
            const keywords = ['综合', '最新', '热', '收录', '点赞', '关注', '视频', '图文'];

            document.querySelectorAll('span, div, a, button').forEach(el => {
                const text = el.innerText?.trim();
                if (text && keywords.some(k => text.includes(k)) && text.length < 15) {
                    results.push({
                        text: text,
                        tag: el.tagName,
                        class: el.className,
                        clickable: el.onclick !== null || el.tagName === 'A' || el.tagName === 'BUTTON'
                    });
                }
            });

            return results;
        }""")

        print("Filter-like elements found:")
        for c in clickables[:20]:
            print(f"  [{c['tag']}] '{c['text']}' (class: {c['class'][:40] if c['class'] else 'none'})")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect_page())
