"""Test filter popup - version 2 with better element detection."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_v2():
    """Find and click the filter button properly."""

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
            print("等待扫码 (60秒)...")
            for i in range(60, 0, -5):
                await asyncio.sleep(5)
                if "captcha" not in page.url:
                    break
            await asyncio.sleep(3)

        # First, find the exact filter button element
        print("\n分析页面上的筛选按钮...")
        filter_info = await page.evaluate("""() => {
            const results = [];

            // Find elements containing "筛选" text
            document.querySelectorAll('*').forEach(el => {
                const text = el.innerText?.trim();
                if (text === '筛选' || (text && text.includes('筛选') && text.length < 10)) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            tag: el.tagName,
                            class: el.className || '',
                            id: el.id || '',
                            text: text,
                            left: Math.round(rect.left),
                            top: Math.round(rect.top),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        });
                    }
                }
            });

            return results;
        }""")

        print(f"找到 {len(filter_info)} 个筛选相关元素:")
        for f in filter_info:
            print(f"  <{f['tag']}> class='{f['class']}' at ({f['left']}, {f['top']}) size={f['width']}x{f['height']}")

        # Take screenshot with annotation
        await page.screenshot(path=str(output_dir / "v2_1_initial.png"))
        print("\n截图1: 初始页面")

        # Click using coordinates if we found the filter button
        if filter_info:
            # Get the rightmost "筛选" element (should be in top right)
            rightmost = max(filter_info, key=lambda x: x['left'])
            print(f"\n选择最右边的筛选按钮: ({rightmost['left']}, {rightmost['top']})")

            # Click using JavaScript to ensure we get it
            clicked = await page.evaluate(f"""() => {{
                const elements = document.querySelectorAll('*');
                for (const el of elements) {{
                    const text = el.innerText?.trim();
                    if (text === '筛选') {{
                        const rect = el.getBoundingClientRect();
                        if (rect.left > 1000) {{  // Right side of screen
                            el.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""")

            print(f"点击结果: {clicked}")
            await asyncio.sleep(2)

            # Take screenshot
            await page.screenshot(path=str(output_dir / "v2_2_after_click.png"))
            print("截图2: 点击后")

            # Check for any new visible elements
            new_elements = await page.evaluate("""() => {
                const results = [];

                // Look for any dropdown/popup that might have appeared
                document.querySelectorAll('[class*="popup"], [class*="dropdown"], [class*="modal"], [class*="drawer"], [class*="panel"], [class*="filter-"], [class*="Filter"]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (rect.height > 50 && style.display !== 'none' && style.opacity !== '0') {
                        results.push({
                            class: el.className,
                            text: el.innerText?.substring(0, 300)
                        });
                    }
                });

                return results;
            }""")

            print(f"\n新出现的弹窗元素: {len(new_elements)}")
            for e in new_elements[:5]:
                print(f"  class: {str(e['class'])[:60]}")
                if e['text']:
                    print(f"  内容: {e['text'][:100]}...")

        # Try hovering instead of clicking
        print("\n\n尝试 hover 筛选按钮...")
        await page.hover("text=筛选")
        await asyncio.sleep(2)
        await page.screenshot(path=str(output_dir / "v2_3_after_hover.png"))
        print("截图3: hover后")

        # Check for dropdown after hover
        dropdown_after_hover = await page.evaluate("""() => {
            const popups = document.querySelectorAll('[class*="popup"], [class*="dropdown"], [class*="menu"]');
            const visible = [];
            popups.forEach(p => {
                const style = window.getComputedStyle(p);
                const rect = p.getBoundingClientRect();
                if (style.display !== 'none' && rect.height > 0) {
                    visible.push({
                        class: p.className,
                        text: p.innerText?.substring(0, 200)
                    });
                }
            });
            return visible;
        }""")

        print(f"Hover后可见的下拉元素: {len(dropdown_after_hover)}")
        for d in dropdown_after_hover[:3]:
            print(f"  {d['text'][:80]}...")

        print("\n\n等待15秒 (可以手动点击筛选看看效果)...")
        await asyncio.sleep(15)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_v2())
