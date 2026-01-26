"""Find filter elements on XHS search page."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def find_filters():
    """Find all filter-like elements."""

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

        # Check for captcha
        if "captcha" in page.url:
            print("等待扫码...")
            for i in range(30, 0, -5):
                await asyncio.sleep(5)
                if "captcha" not in page.url:
                    break

        # Find all text content in the filter area (top part of page)
        print("\n查找页面顶部的所有可点击元素...")

        elements = await page.evaluate("""() => {
            const results = [];

            // Find all elements that might be filter tabs
            document.querySelectorAll('span, div, a, button').forEach(el => {
                const text = el.innerText?.trim();
                const rect = el.getBoundingClientRect();

                // Only look at elements in the top 200px
                if (rect.top > 50 && rect.top < 200 && text && text.length < 20 && text.length > 0) {
                    // Check if it looks clickable
                    const style = window.getComputedStyle(el);
                    const isClickable = el.onclick !== null ||
                                       style.cursor === 'pointer' ||
                                       el.tagName === 'A' ||
                                       el.tagName === 'BUTTON';

                    results.push({
                        text: text,
                        tag: el.tagName,
                        class: el.className?.substring(0, 50) || '',
                        top: Math.round(rect.top),
                        clickable: isClickable
                    });
                }
            });

            // Remove duplicates
            const seen = new Set();
            return results.filter(r => {
                if (seen.has(r.text)) return false;
                seen.add(r.text);
                return true;
            });
        }""")

        print(f"\n找到 {len(elements)} 个元素:\n")
        for e in elements:
            clickable = "✓" if e['clickable'] else " "
            print(f"  [{clickable}] '{e['text']}' ({e['tag']}, top={e['top']})")

        # Also look specifically for the filter bar
        print("\n\n查找筛选栏...")
        filter_bar = await page.evaluate("""() => {
            // Look for elements containing filter keywords
            const keywords = ['综合', '最新', '热门', '收录', '点赞', '视频', '图文', '上三日', '筛选'];
            const found = [];

            document.querySelectorAll('*').forEach(el => {
                const text = el.innerText?.trim() || '';
                if (keywords.some(k => text === k) && !found.includes(text)) {
                    found.push({
                        text: text,
                        tag: el.tagName,
                        class: el.className?.substring(0, 60) || '',
                        parent: el.parentElement?.className?.substring(0, 60) || ''
                    });
                }
            });

            return found;
        }""")

        print(f"找到筛选相关元素:")
        for f in filter_bar:
            print(f"  '{f['text']}' - {f['tag']} class='{f['class']}'")
            print(f"      parent class='{f['parent']}'")

        print("\n等待10秒后关闭...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(find_filters())
