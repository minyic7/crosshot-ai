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

# 检查评论数据结构
JS_CHECK_COMMENTS = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state) return {error: 'no state'};
    if (!state.note) return {error: 'no note', keys: Object.keys(state)};
    if (!state.note.noteDetailMap) return {error: 'no noteDetailMap', noteKeys: Object.keys(state.note)};

    const noteId = Object.keys(state.note.noteDetailMap)[0];
    if (!noteId) return {error: 'no noteId'};

    const detail = state.note.noteDetailMap[noteId];
    if (!detail) return {error: 'no detail'};

    // 查找评论相关的字段
    const result = {
        noteId: noteId,
        detailKeys: Object.keys(detail),
        hasComments: 'comments' in detail,
        commentsType: typeof detail.comments,
    };

    // 如果有评论，获取第一条的结构
    if (detail.comments && Array.isArray(detail.comments) && detail.comments.length > 0) {
        result.commentCount = detail.comments.length;
        result.firstCommentKeys = Object.keys(detail.comments[0]);
        result.firstComment = detail.comments[0];
    }

    // 检查 note 对象中是否有评论相关信息
    if (detail.note) {
        result.noteCommentCount = detail.note.commentCount;
    }

    return result;
}"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()
        page.set_default_timeout(60000)

        # 先搜索获取一个笔记URL
        print("搜索笔记...")
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=melbourne", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 获取第一个笔记链接
        links = await page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item a.cover');
            return Array.from(cards).slice(0, 1).map(a => {
                const href = a.getAttribute('href');
                if (href && href.startsWith('/')) {
                    return 'https://www.xiaohongshu.com' + href;
                }
                return href;
            }).filter(Boolean);
        }""")

        if not links:
            print("未找到笔记链接")
            # 检查是否遇到安全限制
            title = await page.title()
            print(f"页面标题: {title}")
            await page.screenshot(path="/app/data/search_debug.png")
            await browser.close()
            return

        note_url = links[0]
        print(f"\n访问笔记: {note_url[:80]}...")

        await page.goto(note_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # 滚动页面加载评论
        print("滚动加载评论...")
        for i in range(5):
            await page.evaluate("window.scrollBy(0, 300)")
            await asyncio.sleep(0.5)

        # 检查评论结构
        result = await page.evaluate(JS_CHECK_COMMENTS)
        print("\n评论数据结构:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

        # 截图
        await page.screenshot(path="/app/data/note_comments.png")
        print("\n截图: /app/data/note_comments.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
