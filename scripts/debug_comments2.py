import asyncio
from playwright.async_api import async_playwright
import json

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "abRequestId", "value": "15616776-7fcc-543e-a801-c6a72be0492f", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "gid", "value": "yjDd8qSWiWhYyjDd8qSK26x9jJ8Y3FjJCkT80MJq2I0kYxq86uWWj0888Y4jJ8y8qKiy8y4j", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "id_token", "value": "VjEAAJpV6i0Y35Jgm8LeP31c/0DYmKAGcunaNEij+TxEDLmWydcALwY4RJCNBQmLRqS/qyHjVyT4FbbU1Lzc6l5HBK7ildMNcTRr+Wt3f2g55SaLjOfEzGNXFbgolnegSqWUApbV", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70e67c433b4bf5d93b8d", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "xsecappid", "value": "xhs-pc-web", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "websectiga", "value": "cf46039d1971c7b9a650d87269f31ac8fe3bf71d61ebf9d9a0a87efb414b816c", "domain": ".xiaohongshu.com", "path": "/"},
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()
        page.set_default_timeout(60000)

        # 先搜索
        print("搜索笔记...")
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=melbourne", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 获取完整的链接（带token）
        links = await page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item a.cover');
            return Array.from(cards).slice(0, 5).map(a => {
                const href = a.getAttribute('href');
                if (href && href.startsWith('/')) {
                    return 'https://www.xiaohongshu.com' + href;  // 保留完整参数
                }
                return href;
            }).filter(Boolean);
        }""")

        print(f"找到 {len(links)} 个链接")
        for i, link in enumerate(links):
            print(f"  {i+1}. {link[:80]}...")

        if len(links) < 2:
            print("链接不足")
            await browser.close()
            return

        # 访问第二个笔记（通常有更多评论）
        note_url = links[1]
        print(f"\n访问笔记: {note_url}")
        await page.goto(note_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 检查页面
        title = await page.title()
        print(f"页面标题: {title}")

        # 滚动加载
        for i in range(3):
            await page.evaluate("window.scrollBy(0, 400)")
            await asyncio.sleep(0.5)

        # 检查评论
        result = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state) return {error: 'no state'};
            if (!state.note) return {error: 'no note'};
            if (!state.note.noteDetailMap) return {error: 'no noteDetailMap'};

            const noteId = Object.keys(state.note.noteDetailMap)[0];
            const detail = state.note.noteDetailMap[noteId];

            if (!detail.comments) return {error: 'no comments', detailKeys: Object.keys(detail)};

            const list = detail.comments.list || [];
            return {
                noteId: noteId,
                noteTitle: detail.note?.title,
                commentCount: detail.note?.interactInfo?.commentCount,
                listLength: list.length,
                hasMore: detail.comments.hasMore,
                comments: list.slice(0, 3).map(c => ({
                    id: c.id,
                    content: c.content?.slice(0, 50),
                    nickname: c.userInfo?.nickname,
                    likes: c.likeCount,
                    subCount: c.subCommentCount,
                }))
            };
        }""")

        print("\n评论数据:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
