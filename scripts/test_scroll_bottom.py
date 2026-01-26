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

        # 监听所有网络请求
        api_calls = []

        async def handle_response(response):
            url = response.url
            if 'comment' in url and 'api' in url:
                try:
                    body = await response.json()
                    api_calls.append({
                        'url': url[:100],
                        'code': body.get('code'),
                        'comments_count': len(body.get('data', {}).get('comments', [])) if body.get('data') else 0,
                    })
                except:
                    pass

        page.on("response", handle_response)

        # 访问笔记
        print("搜索笔记...")
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=melbourne", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        links = await page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item a.cover');
            return Array.from(cards).slice(0, 3).map(a => a.href).filter(Boolean);
        }""")

        note_url = links[1]
        print(f"访问笔记: {note_url[:70]}...")
        await page.goto(note_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        print(f"初始API调用: {len(api_calls)}")

        # 使用 Playwright 定位器滚动
        print("\n=== 使用 Playwright locator 滚动 ===")

        # 找到note-scroller
        scroller = page.locator('.note-scroller')
        if await scroller.count() > 0:
            # 滚动到底部多次
            for i in range(8):
                # 滚动到底部
                await scroller.evaluate("""el => {
                    el.scrollTop = el.scrollHeight;
                    // 触发多种事件
                    el.dispatchEvent(new Event('scroll', { bubbles: true }));
                    el.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, bubbles: true }));
                }""")
                await asyncio.sleep(2)

                # 检查状态
                info = await page.evaluate("""() => {
                    const state = window.__INITIAL_STATE__;
                    if (!state?.note?.noteDetailMap) return null;
                    const noteId = Object.keys(state.note.noteDetailMap)[0];
                    const detail = state.note.noteDetailMap[noteId];
                    return {
                        count: detail.comments?.list?.length || 0,
                        hasMore: detail.comments?.hasMore,
                        loading: detail.comments?.loading,
                    };
                }""")

                print(f"滚动 {i+1}: 评论={info['count']}, hasMore={info['hasMore']}, loading={info['loading']}, API调用={len(api_calls)}")

                if not info['hasMore']:
                    print("已加载全部")
                    break

        # 总结
        print(f"\n=== API调用详情 ({len(api_calls)}) ===")
        for call in api_calls:
            print(f"  code={call['code']}, comments={call['comments_count']}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
