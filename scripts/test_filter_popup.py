"""Test the filter popup on XHS search page."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from apps.config import get_settings


async def test_filter_popup():
    """Click filter button and explore the popup."""

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
                print(f"  剩余 {i} 秒...")
                await asyncio.sleep(5)
                if "captcha" not in page.url:
                    print("  登录成功!")
                    break
            await asyncio.sleep(3)

        # Screenshot before
        await page.screenshot(path=str(output_dir / "popup_1_before.png"))
        print("\n截图1: 点击筛选前")

        # Click the "筛选" button (it's in the top right)
        print("\n点击右上角 '筛选' 按钮...")
        try:
            # Try different selectors for the filter button
            filter_btn = page.locator("text=筛选").first
            if await filter_btn.count() == 0:
                filter_btn = page.locator("div.filter").first
            if await filter_btn.count() == 0:
                filter_btn = page.locator("[class*='filter']").first

            print(f"找到筛选按钮: {await filter_btn.count()} 个")
            await filter_btn.click()
            await asyncio.sleep(2)

            # Screenshot after click - should show popup
            await page.screenshot(path=str(output_dir / "popup_2_after_click.png"))
            print("截图2: 点击筛选后 (应该显示弹窗)")

            # Find all text content in the popup
            popup_content = await page.evaluate("""() => {
                const results = {
                    sortOptions: [],
                    noteTypes: [],
                    timeOptions: [],
                    searchScope: [],
                    locationOptions: [],
                    allText: []
                };

                // Look for popup/modal elements
                const popups = document.querySelectorAll(
                    '[class*="popup"], [class*="modal"], [class*="drawer"], ' +
                    '[class*="panel"], [class*="dropdown"], [class*="filter-content"], ' +
                    '[class*="overlay"], [class*="dialog"]'
                );

                popups.forEach(popup => {
                    const rect = popup.getBoundingClientRect();
                    const style = window.getComputedStyle(popup);
                    if (rect.height > 50 && style.display !== 'none') {
                        // Get all text from this popup
                        const text = popup.innerText?.trim();
                        if (text) {
                            results.allText.push({
                                class: popup.className?.substring(0, 60) || '',
                                text: text.substring(0, 500)
                            });
                        }
                    }
                });

                // Also look for specific filter-related text
                const filterKeywords = ['综合', '最新', '最多点赞', '最多评论', '最多收藏',
                                       '视频', '图文', '不限',
                                       '一天内', '一周内', '半年内',
                                       '已看过', '未看过', '已关注',
                                       '同城', '附近', '排序'];

                document.querySelectorAll('*').forEach(el => {
                    const text = el.innerText?.trim();
                    if (text && filterKeywords.some(k => text === k)) {
                        const rect = el.getBoundingClientRect();
                        if (rect.height > 0) {
                            results.sortOptions.push({
                                text: text,
                                tag: el.tagName,
                                class: el.className?.substring(0, 40) || ''
                            });
                        }
                    }
                });

                return results;
            }""")

            print("\n弹窗内容:")
            if popup_content['allText']:
                for item in popup_content['allText'][:3]:
                    print(f"\n  class: {item['class']}")
                    print(f"  内容: {item['text'][:200]}...")

            print("\n\n筛选选项:")
            seen = set()
            for opt in popup_content['sortOptions']:
                if opt['text'] not in seen:
                    seen.add(opt['text'])
                    print(f"  - '{opt['text']}' ({opt['tag']})")

            # Try clicking "最新" option
            print("\n\n尝试点击 '最新' 选项...")
            newest_btn = page.locator("text=最新").first
            if await newest_btn.count() > 0:
                await newest_btn.click()
                await asyncio.sleep(2)
                await page.screenshot(path=str(output_dir / "popup_3_after_newest.png"))
                print("截图3: 选择'最新'后")

                # Check URL change
                print(f"当前 URL: {page.url}")

            # Try clicking "一天内" option
            print("\n尝试点击 '一天内' 选项...")
            one_day_btn = page.locator("text=一天内").first
            if await one_day_btn.count() > 0:
                await one_day_btn.click()
                await asyncio.sleep(2)
                await page.screenshot(path=str(output_dir / "popup_4_after_oneday.png"))
                print("截图4: 选择'一天内'后")
                print(f"当前 URL: {page.url}")

            # Look for confirm/apply button
            print("\n查找确认按钮...")
            confirm_btn = page.locator("text=确定").first
            if await confirm_btn.count() == 0:
                confirm_btn = page.locator("text=确认").first
            if await confirm_btn.count() == 0:
                confirm_btn = page.locator("text=应用").first

            if await confirm_btn.count() > 0:
                await confirm_btn.click()
                await asyncio.sleep(3)
                await page.screenshot(path=str(output_dir / "popup_5_after_confirm.png"))
                print("截图5: 确认筛选后")
                print(f"最终 URL: {page.url}")

                # Extract notes with new filter
                notes = await page.evaluate("""() => {
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

                print("\n筛选后前5条笔记:")
                for i, n in enumerate(notes, 1):
                    print(f"  {i}. {n['title']}... ({n['likes']})")

        except Exception as e:
            print(f"操作失败: {e}")
            import traceback
            traceback.print_exc()

        print("\n\n等待10秒后关闭...")
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_filter_popup())
