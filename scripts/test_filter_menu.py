"""Click filter and explore the dropdown menu."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_menu():
    """Click filter and see what options appear."""

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

        # Screenshot before
        await page.screenshot(path=str(output_dir / "menu_1_before.png"))
        print("截图1: 点击前")

        # Click the filter div
        print("\n点击 '筛选' ...")
        filter_div = page.locator("div.filter")
        await filter_div.click()
        await asyncio.sleep(2)

        # Screenshot after click
        await page.screenshot(path=str(output_dir / "menu_2_after.png"))
        print("截图2: 点击后")

        # Find any new elements that appeared
        print("\n查找弹出的菜单元素...")
        menu_items = await page.evaluate("""() => {
            const results = [];

            // Look for common dropdown/popup classes
            const popups = document.querySelectorAll(
                '[class*="popup"], [class*="dropdown"], [class*="menu"], ' +
                '[class*="modal"], [class*="overlay"], [class*="panel"], ' +
                '[class*="select"], [class*="option"]'
            );

            popups.forEach(el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                // Only visible elements
                if (style.display !== 'none' && style.visibility !== 'hidden' && rect.height > 0) {
                    results.push({
                        tag: el.tagName,
                        class: el.className || '',
                        text: el.innerText?.trim().substring(0, 100) || '',
                        visible: true
                    });
                }
            });

            return results;
        }""")

        print(f"\n找到 {len(menu_items)} 个弹出元素:")
        for m in menu_items[:15]:
            print(f"  <{m['tag']}> class='{str(m['class'])[:40]}'")
            if m['text']:
                print(f"      text: {m['text'][:60]}")

        # Also check for any element that contains sort-related text
        print("\n\n查找包含排序关键词的元素...")
        sort_elements = await page.evaluate("""() => {
            const keywords = ['排序', '综合排序', '最新', '最热', '时间', '热度', '收录', '点赞'];
            const results = [];

            document.querySelectorAll('*').forEach(el => {
                const text = el.innerText?.trim() || '';
                if (text && keywords.some(k => text === k || text.includes('排序'))) {
                    const rect = el.getBoundingClientRect();
                    if (rect.height > 0) {
                        results.push({
                            tag: el.tagName,
                            class: el.className || '',
                            text: text.substring(0, 50)
                        });
                    }
                }
            });

            // Dedupe by text
            const seen = new Set();
            return results.filter(r => {
                if (seen.has(r.text)) return false;
                seen.add(r.text);
                return true;
            });
        }""")

        print(f"排序相关元素:")
        for s in sort_elements[:10]:
            print(f"  '{s['text']}' ({s['tag']})")

        print("\n\n等待10秒后关闭...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_menu())
