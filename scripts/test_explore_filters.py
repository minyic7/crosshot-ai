"""Explore all interactive elements on XHS search page."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def explore_page():
    """Explore all clickable elements."""

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
            for i in range(30, 0, -5):
                await asyncio.sleep(5)
                if "captcha" not in page.url:
                    break
            await asyncio.sleep(3)

        # Get all buttons in the filter area
        print("\n查找所有 BUTTON 元素...")
        buttons = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('button, [role="button"]').forEach(el => {
                const text = el.innerText?.trim();
                const rect = el.getBoundingClientRect();
                if (text && rect.top < 300) {
                    results.push({
                        text: text,
                        class: el.className || '',
                        top: Math.round(rect.top)
                    });
                }
            });
            return results;
        }""")

        print("按钮列表:")
        for b in buttons:
            print(f"  [{b['top']}px] '{b['text']}' (class: {b['class'][:40]})")

        # Get all divs with 'filter' in class
        print("\n\n查找 class 包含 'filter' 的元素...")
        filter_elements = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('[class*="filter"], [class*="sort"], [class*="order"]').forEach(el => {
                results.push({
                    tag: el.tagName,
                    class: el.className,
                    text: el.innerText?.trim().substring(0, 50) || ''
                });
            });
            return results;
        }""")

        print("Filter/Sort 相关元素:")
        for f in filter_elements[:10]:
            print(f"  <{f['tag']}> class='{f['class'][:50]}' text='{f['text']}'")

        # Take a high-res screenshot and print all visible text
        await page.screenshot(path=str(output_dir / "explore_full.png"), full_page=True)
        print("\n\n完整页面截图已保存")

        # Get all unique short texts from the page header
        print("\n\n页面顶部 300px 内所有唯一文本:")
        texts = await page.evaluate("""() => {
            const seen = new Set();
            const results = [];
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length === 0) {  // Only leaf nodes
                    const text = el.innerText?.trim();
                    const rect = el.getBoundingClientRect();
                    if (text && text.length < 20 && text.length > 0 && rect.top < 300 && !seen.has(text)) {
                        seen.add(text);
                        results.push({text, top: Math.round(rect.top)});
                    }
                }
            });
            return results.sort((a, b) => a.top - b.top);
        }""")

        for t in texts:
            print(f"  [{t['top']}px] {t['text']}")

        print("\n\n等待10秒...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(explore_page())
