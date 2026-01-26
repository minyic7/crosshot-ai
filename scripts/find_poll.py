import asyncio
from playwright.async_api import async_playwright
import json

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70c195403b4b8a6426a1", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        # 搜索带投票的笔记
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=投票 选择", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 获取搜索结果的链接
        links = await page.evaluate(
            """() => {
            const cards = document.querySelectorAll('section.note-item a[href*="search_result/"]');
            return Array.from(cards).slice(0, 15).map(a => a.href);
        }"""
        )

        print(f"找到 {len(links)} 篇笔记")

        # 逐个检查是否有投票
        for i, link in enumerate(links):
            await page.goto(link, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # 检查页面内容
            title = await page.evaluate("() => document.querySelector('#detail-title')?.innerText || ''")
            html = await page.content()

            # 检查投票相关元素
            has_vote_class = "vote" in html.lower() and "class" in html
            has_poll = "poll" in html.lower()

            print(f"{i+1}. {title[:40]}...")
            print(f"   vote in html: {has_vote_class}, poll: {has_poll}")

            # 查看 __INITIAL_STATE__ 中是否有投票数据
            state_data = await page.evaluate(
                """() => {
                const state = window.__INITIAL_STATE__;
                if (!state || !state.note || !state.note.noteDetailMap) return null;
                const noteId = Object.keys(state.note.noteDetailMap)[0];
                const detail = state.note.noteDetailMap[noteId];
                if (!detail || !detail.note) return null;
                const n = detail.note;
                return {
                    hasVote: !!n.vote,
                    vote: n.vote || null,
                    hasInteractiveInfo: !!n.interactiveInfo,
                    interactiveInfo: n.interactiveInfo || null
                };
            }"""
            )

            if state_data:
                print(f"   hasVote: {state_data.get('hasVote')}")
                if state_data.get("vote"):
                    print(f"   >>> 找到投票数据!")
                    print(json.dumps(state_data["vote"], ensure_ascii=False, indent=2))
                    await page.screenshot(path="/app/poll_note.png")
                    print("   截图保存到 /app/poll_note.png")
                    break
                if state_data.get("interactiveInfo"):
                    print(f"   interactiveInfo: {state_data['interactiveInfo']}")

            if i >= 14:
                print("\n未找到带投票的笔记，尝试其他搜索词...")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
