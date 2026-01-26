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

        # 监听网络请求
        comment_requests = []

        async def handle_request(request):
            if 'comment' in request.url.lower():
                comment_requests.append({
                    'url': request.url,
                    'method': request.method,
                })

        page.on("request", handle_request)

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

        # 检查页面上的"加载更多"相关元素
        load_more_info = await page.evaluate("""() => {
            const results = [];

            // 查找包含"更多"、"加载"、"展开"文字的元素
            const allElements = document.querySelectorAll('*');
            for (const el of allElements) {
                const text = el.textContent?.trim();
                if (text && (text.includes('更多') || text.includes('加载') || text.includes('展开') || text.includes('查看'))) {
                    if (text.length < 30 && el.tagName !== 'SCRIPT' && el.tagName !== 'STYLE') {
                        results.push({
                            tag: el.tagName,
                            text: text.slice(0, 50),
                            className: el.className?.slice?.(0, 50) || '',
                            clickable: el.onclick !== null || el.tagName === 'BUTTON' || el.tagName === 'A',
                        });
                    }
                }
            }

            // 去重
            const seen = new Set();
            return results.filter(r => {
                const key = r.text + r.className;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).slice(0, 20);
        }""")

        print("\n=== 发现的'加载更多'相关元素 ===")
        for item in load_more_info:
            print(f"  <{item['tag']}> '{item['text']}' class='{item['className']}'")

        # 查找评论相关的网络请求
        print(f"\n=== 评论相关请求 ({len(comment_requests)}) ===")
        for req in comment_requests[:5]:
            print(f"  {req['method']} {req['url'][:80]}...")

        # 尝试点击"查看更多评论"或"展开"按钮
        print("\n=== 尝试点击加载更多 ===")

        # 方法1: 点击"展开更多评论"
        clicked = await page.evaluate("""() => {
            // 查找并点击展开按钮
            const btns = document.querySelectorAll('[class*="show-more"], [class*="load-more"], [class*="expand"]');
            for (const btn of btns) {
                if (btn.textContent.includes('更多') || btn.textContent.includes('展开')) {
                    btn.click();
                    return btn.textContent.trim();
                }
            }

            // 查找文字包含"展开"的可点击元素
            const allEls = document.querySelectorAll('span, div, button, a');
            for (const el of allEls) {
                const text = el.textContent?.trim();
                if (text && text.length < 20 && (text.includes('展开') || text.includes('更多评论') || text.includes('查看更多'))) {
                    el.click();
                    return text;
                }
            }
            return null;
        }""")

        if clicked:
            print(f"点击了: '{clicked}'")
            await asyncio.sleep(2)

            # 检查评论数是否变化
            new_count = await page.evaluate("""() => {
                const state = window.__INITIAL_STATE__;
                if (!state?.note?.noteDetailMap) return 0;
                const noteId = Object.keys(state.note.noteDetailMap)[0];
                return state.note.noteDetailMap[noteId]?.comments?.list?.length || 0;
            }""")
            print(f"点击后评论数: {new_count}")
        else:
            print("未找到可点击的加载更多按钮")

        # 截图查看评论区
        await page.screenshot(path="/app/data/comments_area.png")
        print("\n截图: /app/data/comments_area.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
