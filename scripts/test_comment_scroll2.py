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

        # 监听评论API
        comment_api_count = [0]

        async def handle_response(response):
            if 'comment/page' in response.url:
                comment_api_count[0] += 1
                print(f"  [API] 评论请求 #{comment_api_count[0]}")

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

        # 查找所有可能的滚动容器
        containers = await page.evaluate("""() => {
            const results = [];
            const allDivs = document.querySelectorAll('div');
            for (const div of allDivs) {
                const style = getComputedStyle(div);
                // 找有滚动条的容器
                if ((style.overflow === 'auto' || style.overflow === 'scroll' ||
                     style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                    div.scrollHeight > div.clientHeight) {
                    results.push({
                        className: div.className?.slice(0, 60),
                        scrollHeight: div.scrollHeight,
                        clientHeight: div.clientHeight,
                        scrollTop: div.scrollTop,
                    });
                }
            }
            return results;
        }""")

        print(f"\n找到 {len(containers)} 个可滚动容器:")
        for c in containers[:5]:
            print(f"  {c['className'][:40]}... h={c['scrollHeight']}/{c['clientHeight']}")

        # 找到评论相关的滚动容器
        print("\n=== 直接操作滚动容器 ===")

        initial_count = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state?.note?.noteDetailMap) return 0;
            const noteId = Object.keys(state.note.noteDetailMap)[0];
            return state.note.noteDetailMap[noteId]?.comments?.list?.length || 0;
        }""")
        print(f"初始评论数: {initial_count}")

        # 逐个尝试滚动容器
        for i in range(5):
            result = await page.evaluate("""(iteration) => {
                // 找所有可滚动的div
                const scrollables = [];
                document.querySelectorAll('div').forEach(div => {
                    if (div.scrollHeight > div.clientHeight + 50) {
                        scrollables.push(div);
                    }
                });

                let scrolled = [];
                for (const div of scrollables) {
                    const before = div.scrollTop;
                    div.scrollTop += 500;
                    if (div.scrollTop !== before) {
                        scrolled.push({
                            className: div.className?.slice(0, 30),
                            from: before,
                            to: div.scrollTop,
                        });

                        // 触发scroll事件
                        div.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }
                }
                return scrolled;
            }""", i)

            print(f"滚动 {i+1}: 滚动了 {len(result)} 个容器")
            for r in result[:3]:
                print(f"  {r['className']}... {r['from']} -> {r['to']}")

            await asyncio.sleep(1.5)

            # 检查评论数
            new_count = await page.evaluate("""() => {
                const state = window.__INITIAL_STATE__;
                if (!state?.note?.noteDetailMap) return 0;
                const noteId = Object.keys(state.note.noteDetailMap)[0];
                return state.note.noteDetailMap[noteId]?.comments?.list?.length || 0;
            }""")

            if new_count != initial_count:
                print(f"  评论数变化: {initial_count} -> {new_count}")
                initial_count = new_count

        print(f"\n最终评论数: {initial_count}")
        print(f"评论API调用次数: {comment_api_count[0]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
