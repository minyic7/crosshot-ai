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


async def get_comment_count(page):
    """获取当前加载的评论数量"""
    return await page.evaluate("""() => {
        const state = window.__INITIAL_STATE__;
        if (!state?.note?.noteDetailMap) return {count: 0, hasMore: false};
        const noteId = Object.keys(state.note.noteDetailMap)[0];
        const detail = state.note.noteDetailMap[noteId];
        return {
            count: detail.comments?.list?.length || 0,
            hasMore: detail.comments?.hasMore || false,
            cursor: detail.comments?.cursor || null,
        };
    }""")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()
        page.set_default_timeout(60000)

        # 搜索并获取有评论的笔记
        print("搜索笔记...")
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=melbourne", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        links = await page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item a.cover');
            return Array.from(cards).slice(0, 3).map(a => a.href).filter(Boolean);
        }""")

        note_url = links[1]  # 选第二个（有更多评论）
        print(f"访问笔记: {note_url[:70]}...")
        await page.goto(note_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 初始评论数
        info = await get_comment_count(page)
        print(f"\n初始: {info['count']} 条评论, hasMore={info['hasMore']}")

        # 尝试滚动加载更多
        print("\n=== 开始滚动测试 ===")
        for i in range(10):
            # 滚动到评论区底部
            await page.evaluate("""() => {
                // 找到评论区容器并滚动
                const commentSection = document.querySelector('.comments-container, .comment-list, [class*="comment"]');
                if (commentSection) {
                    commentSection.scrollTop = commentSection.scrollHeight;
                }
                // 也滚动整个页面
                window.scrollBy(0, 800);
            }""")
            await asyncio.sleep(1.5)

            new_info = await get_comment_count(page)
            if new_info['count'] != info['count']:
                print(f"滚动 {i+1}: {new_info['count']} 条评论 (+{new_info['count'] - info['count']})")
                info = new_info
            else:
                print(f"滚动 {i+1}: 无变化 ({info['count']} 条)")

            # 检查是否还有更多
            if not new_info['hasMore']:
                print("已加载全部评论")
                break

        # 最终统计
        final = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state?.note?.noteDetailMap) return null;
            const noteId = Object.keys(state.note.noteDetailMap)[0];
            const detail = state.note.noteDetailMap[noteId];
            const list = detail.comments?.list || [];

            return {
                totalComments: list.length,
                hasMore: detail.comments?.hasMore,
                // 统计所有子评论
                totalSubComments: list.reduce((sum, c) => sum + (c.subComments?.length || 0), 0),
                // 有更多子评论的评论数
                commentsWithMoreSubs: list.filter(c => c.subCommentHasMore).length,
            };
        }""")

        print(f"\n=== 最终结果 ===")
        print(f"主评论: {final['totalComments']} 条")
        print(f"已加载子评论: {final['totalSubComments']} 条")
        print(f"还有更多子评论的: {final['commentsWithMoreSubs']} 条")
        print(f"还有更多主评论: {final['hasMore']}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
