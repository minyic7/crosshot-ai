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

# 深入检查评论数据结构
JS_CHECK_COMMENTS_DETAIL = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state || !state.note || !state.note.noteDetailMap) return {error: 'no data'};

    const noteId = Object.keys(state.note.noteDetailMap)[0];
    const detail = state.note.noteDetailMap[noteId];
    const comments = detail.comments;

    // 检查 comments 的结构
    const result = {
        commentsType: typeof comments,
        isArray: Array.isArray(comments),
        commentsKeys: comments ? Object.keys(comments) : null,
    };

    // 如果是对象，检查其属性
    if (comments && typeof comments === 'object' && !Array.isArray(comments)) {
        for (const key of Object.keys(comments)) {
            const val = comments[key];
            result[`comments.${key}`] = {
                type: typeof val,
                isArray: Array.isArray(val),
                length: Array.isArray(val) ? val.length : null,
            };
        }

        // 如果有 comments.list 或类似的数组
        if (comments.list && Array.isArray(comments.list) && comments.list.length > 0) {
            result.firstItem = comments.list[0];
        }
    }

    // 检查 note 里的评论相关数据
    if (detail.note) {
        result.noteComments = detail.note.commentCount;
        result.noteInteractInfo = detail.note.interactInfo;
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

        # 先搜索获取一个有评论的笔记
        print("搜索笔记...")
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=melbourne", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        links = await page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item a.cover');
            return Array.from(cards).slice(0, 3).map(a => {
                const href = a.getAttribute('href');
                if (href && href.startsWith('/')) {
                    return 'https://www.xiaohongshu.com' + href;
                }
                return href;
            }).filter(Boolean);
        }""")

        if not links:
            print("未找到笔记")
            await browser.close()
            return

        # 测试多个笔记
        for note_url in links:
            print(f"\n{'='*60}")
            print(f"访问: {note_url[:70]}...")

            await page.goto(note_url, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            # 滚动加载
            for i in range(3):
                await page.evaluate("window.scrollBy(0, 400)")
                await asyncio.sleep(0.5)

            result = await page.evaluate(JS_CHECK_COMMENTS_DETAIL)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
