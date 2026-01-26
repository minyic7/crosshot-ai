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

        # 直接访问有评论的笔记
        url = "https://www.xiaohongshu.com/search_result/67bc3cdb0000000029018bee"
        print(f"访问: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 检查页面状态
        title = await page.title()
        print(f"页面标题: {title}")

        # 检查 __INITIAL_STATE__
        result = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state) return {error: 'no state'};
            if (!state.note) return {error: 'no note', stateKeys: Object.keys(state)};
            if (!state.note.noteDetailMap) return {error: 'no noteDetailMap', noteKeys: Object.keys(state.note)};

            const noteId = Object.keys(state.note.noteDetailMap)[0];
            if (!noteId) return {error: 'no noteId'};

            const detail = state.note.noteDetailMap[noteId];
            return {
                noteId: noteId,
                detailKeys: Object.keys(detail),
                hasComments: !!detail.comments,
                commentsKeys: detail.comments ? Object.keys(detail.comments) : null,
                commentsList: detail.comments && detail.comments.list ? detail.comments.list.length : 0,
                firstComment: detail.comments && detail.comments.list && detail.comments.list[0] ?
                    {
                        id: detail.comments.list[0].id,
                        content: detail.comments.list[0].content,
                        nickname: detail.comments.list[0].userInfo?.nickname
                    } : null,
            };
        }""")

        print("\n结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
