"""Test clicking the filter dropdown."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_dropdown():
    """Click filter dropdown and see options."""

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

        # Take initial screenshot
        await page.screenshot(path=str(output_dir / "filter_1_before.png"))
        print("\n截图1: 点击筛选前")

        # Click the "筛选" button
        print("\n点击 '筛选' 按钮...")
        try:
            filter_btn = page.locator("div.filter").first
            await filter_btn.click()
            await asyncio.sleep(2)

            # Take screenshot after clicking
            await page.screenshot(path=str(output_dir / "filter_2_dropdown.png"))
            print("截图2: 筛选下拉菜单")

            # Find all options in the dropdown
            options = await page.evaluate("""() => {
                // Look for any newly visible elements
                const results = [];
                document.querySelectorAll('*').forEach(el => {
                    const text = el.innerText?.trim();
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);

                    // Look for visible elements that appeared after click
                    if (text && text.length < 30 && text.length > 0 &&
                        rect.top > 100 && rect.top < 400 &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden') {

                        const keywords = ['排序', '时间', '综合', '最新', '最热', '收录', '点赞', '筛选'];
                        if (keywords.some(k => text.includes(k))) {
                            results.push({
                                text: text,
                                tag: el.tagName,
                                class: el.className?.substring(0, 40) || ''
                            });
                        }
                    }
                });

                // Dedupe
                const seen = new Set();
                return results.filter(r => {
                    if (seen.has(r.text)) return false;
                    seen.add(r.text);
                    return true;
                });
            }""")

            print("\n筛选选项:")
            for o in options:
                print(f"  '{o['text']}' ({o['tag']}, class={o['class']})")

        except Exception as e:
            print(f"点击失败: {e}")

        print("\n等待10秒...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_dropdown())
