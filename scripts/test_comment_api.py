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

        # 收集所有评论API响应
        comment_responses = []

        async def handle_response(response):
            url = response.url
            if 'comment' in url and 'api' in url:
                try:
                    body = await response.json()
                    comment_responses.append({
                        'url': url,
                        'status': response.status,
                        'body': body,
                    })
                    print(f"  [API] {url[:60]}... code={body.get('code')}")
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
        print(f"\n访问笔记: {note_url[:70]}...")
        await page.goto(note_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        print(f"\n捕获到 {len(comment_responses)} 个评论API响应")

        # 分析第一个评论API响应
        if comment_responses:
            resp = comment_responses[0]
            body = resp['body']
            print(f"\n=== 评论API响应分析 ===")
            print(f"URL: {resp['url'][:100]}...")
            print(f"code: {body.get('code')}")
            print(f"success: {body.get('success')}")

            if body.get('data'):
                data = body['data']
                print(f"\ndata keys: {list(data.keys())}")
                if 'comments' in data:
                    comments = data['comments']
                    print(f"comments count: {len(comments)}")
                    print(f"has_more: {data.get('has_more')}")
                    print(f"cursor: {data.get('cursor')}")

                    if comments:
                        print(f"\n第一条评论结构:")
                        first = comments[0]
                        for key in list(first.keys())[:15]:
                            val = first[key]
                            if isinstance(val, (str, int, bool)):
                                print(f"  {key}: {str(val)[:50]}")
                            else:
                                print(f"  {key}: {type(val).__name__}")

        # 尝试触发加载更多评论
        print("\n\n=== 触发加载更多 ===")

        # 滚动到评论区底部
        await page.evaluate("""() => {
            const comments = document.querySelector('.comments-container');
            if (comments) comments.scrollTop = comments.scrollHeight;
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        await asyncio.sleep(2)

        # 点击"展开更多回复"
        expand_count = await page.evaluate("""() => {
            let count = 0;
            const showMoreBtns = document.querySelectorAll('.show-more');
            for (const btn of showMoreBtns) {
                if (btn.textContent.includes('展开')) {
                    btn.click();
                    count++;
                }
            }
            return count;
        }""")
        print(f"点击了 {expand_count} 个'展开回复'按钮")
        await asyncio.sleep(2)

        print(f"\n点击后新增 {len(comment_responses) - 1} 个API响应")

        # 分析新的响应
        for resp in comment_responses[1:]:
            url = resp['url']
            body = resp['body']
            if 'sub_comment' in url or 'sub' in url:
                print(f"\n子评论API: {url[:80]}...")
                if body.get('data') and body['data'].get('comments'):
                    print(f"  子评论数: {len(body['data']['comments'])}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
