import asyncio
from playwright.async_api import async_playwright
import json

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70c195403b4b8a6426a1", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
]


async def check_note(page, link):
    """检查单个笔记是否有投票"""
    await page.goto(link, wait_until="domcontentloaded")
    await asyncio.sleep(3)

    title = await page.evaluate("() => document.querySelector('#detail-title')?.innerText || ''")

    # 检查 __INITIAL_STATE__ 中所有字段
    data = await page.evaluate(
        """() => {
        const state = window.__INITIAL_STATE__;
        if (!state || !state.note || !state.note.noteDetailMap) return null;
        const noteId = Object.keys(state.note.noteDetailMap)[0];
        const detail = state.note.noteDetailMap[noteId];
        if (!detail || !detail.note) return null;
        const n = detail.note;

        // 返回所有可能相关的字段
        return {
            title: n.title,
            type: n.type,
            vote: n.vote,
            voteInfo: n.voteInfo,
            interactiveInfo: n.interactiveInfo,
            interact: n.interact,
            noteCard: n.noteCard,
            extInfo: n.extInfo,
            // 列出所有 keys
            allKeys: Object.keys(n)
        };
    }"""
    )

    return title, data


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        # 多个搜索词尝试
        keywords = ["帮我选", "选哪个", "A还是B", "你们选", "帮忙选一下"]

        for keyword in keywords:
            print(f"\n=== 搜索: {keyword} ===")
            await page.goto(f"https://www.xiaohongshu.com/search_result?keyword={keyword}", wait_until="domcontentloaded")
            await asyncio.sleep(5)

            links = await page.evaluate(
                """() => {
                const cards = document.querySelectorAll('section.note-item a[href*="search_result/"]');
                return Array.from(cards).slice(0, 5).map(a => a.href);
            }"""
            )

            for i, link in enumerate(links):
                title, data = await check_note(page, link)
                print(f"{i+1}. {title[:35]}...")

                if data:
                    # 检查是否有特殊字段
                    keys = data.get("allKeys", [])
                    special_keys = [k for k in keys if k not in ["title", "desc", "noteId", "type", "user", "imageList", "tagList", "interactInfo", "time", "lastUpdateTime", "ipLocation", "shareInfo", "noteType", "auditStatus"]]
                    if special_keys:
                        print(f"   特殊字段: {special_keys}")

                    if data.get("vote"):
                        print(f"   >>> vote 数据: {data['vote']}")
                    if data.get("voteInfo"):
                        print(f"   >>> voteInfo: {data['voteInfo']}")
                    if data.get("interactiveInfo"):
                        print(f"   >>> interactiveInfo: {data['interactiveInfo']}")

        # 直接访问一个已知的互动笔记看看结构
        print("\n=== 检查笔记字段结构 ===")
        await page.goto("https://www.xiaohongshu.com/explore/67556a3a000000000603bf05", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        all_keys = await page.evaluate(
            """() => {
            const state = window.__INITIAL_STATE__;
            if (!state || !state.note || !state.note.noteDetailMap) return [];
            const noteId = Object.keys(state.note.noteDetailMap)[0];
            const detail = state.note.noteDetailMap[noteId];
            if (!detail || !detail.note) return [];
            return Object.keys(detail.note);
        }"""
        )
        print(f"笔记所有字段: {all_keys}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
