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

        # 搜索并获取笔记
        print("搜索笔记...")
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=melbourne", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 获取第二个笔记链接（有更多评论）
        links = await page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item a.cover');
            return Array.from(cards).slice(0, 3).map(a => a.href).filter(Boolean);
        }""")

        if len(links) < 2:
            print("链接不足")
            await browser.close()
            return

        note_url = links[1]
        print(f"访问笔记: {note_url[:80]}...")
        await page.goto(note_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 检查评论区是否有排序选项
        sort_info = await page.evaluate("""() => {
            // 查找排序相关的UI元素
            const sortBtns = document.querySelectorAll('[class*="sort"], [class*="tab"], [class*="filter"]');
            const sortTexts = [];
            sortBtns.forEach(el => {
                if (el.textContent.includes('热门') || el.textContent.includes('最新') ||
                    el.textContent.includes('热度') || el.textContent.includes('时间')) {
                    sortTexts.push({
                        text: el.textContent.trim().slice(0, 30),
                        className: el.className
                    });
                }
            });

            // 检查 __INITIAL_STATE__ 中的评论排序信息
            const state = window.__INITIAL_STATE__;
            if (!state || !state.note || !state.note.noteDetailMap) return { sortTexts, stateError: 'no state' };

            const noteId = Object.keys(state.note.noteDetailMap)[0];
            const detail = state.note.noteDetailMap[noteId];

            return {
                sortTexts,
                commentsKeys: detail.comments ? Object.keys(detail.comments) : null,
                // 检查是否有排序相关字段
                commentsSortType: detail.comments?.sortType,
                commentsSort: detail.comments?.sort,
                commentsOrder: detail.comments?.order,
                // 检查第一条评论的完整结构
                firstCommentKeys: detail.comments?.list?.[0] ? Object.keys(detail.comments.list[0]) : null,
                // 检查子评论结构
                firstCommentSubKeys: detail.comments?.list?.[0]?.subComments?.[0] ?
                    Object.keys(detail.comments.list[0].subComments[0]) : null,
                // 子评论是否有 hasMore
                subCommentHasMore: detail.comments?.list?.[0]?.subCommentHasMore,
                subCommentCursor: detail.comments?.list?.[0]?.subCommentCursor,
            };
        }""")

        print("\n=== 排序信息 ===")
        print(json.dumps(sort_info, indent=2, ensure_ascii=False))

        # 检查完整的评论数据
        full_comments = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state?.note?.noteDetailMap) return null;

            const noteId = Object.keys(state.note.noteDetailMap)[0];
            const detail = state.note.noteDetailMap[noteId];
            const comments = detail.comments;

            if (!comments) return null;

            return {
                // 评论列表元数据
                hasMore: comments.hasMore,
                cursor: comments.cursor,
                loading: comments.loading,
                listLength: comments.list?.length || 0,
                // 完整的第一条评论（包含所有字段）
                firstComment: comments.list?.[0] || null,
            };
        }""")

        print("\n=== 评论完整结构 ===")
        print(json.dumps(full_comments, indent=2, ensure_ascii=False, default=str))

        # 截图看看评论区UI
        await page.screenshot(path="/app/data/comment_ui.png", full_page=False)
        print("\n截图保存: /app/data/comment_ui.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
