import asyncio
from playwright.async_api import async_playwright
import json

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "abRequestId", "value": "15616776-7fcc-543e-a801-c6a72be0492f", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "gid", "value": "yjDd8qSWiWhYyjDd8qSK26x9jJ8Y3FjJCkT80MJq2I0kYxq86uWWj0888Y4jJ8y8qKiy8y4j", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70c195403b4b8a6426a1", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "xsecappid", "value": "xhs-pc-web", "domain": ".xiaohongshu.com", "path": "/"},
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        api_responses = []

        # 拦截 API 请求
        async def handle_response(response):
            url = response.url
            if 'api' in url or 'feed' in url or 'search' in url:
                try:
                    if 'application/json' in response.headers.get('content-type', ''):
                        body = await response.json()
                        api_responses.append({
                            'url': url[:100],
                            'status': response.status,
                            'body_keys': list(body.keys()) if isinstance(body, dict) else type(body).__name__
                        })
                        # 检查是否有 vote 相关
                        body_str = json.dumps(body)
                        if 'vote' in body_str.lower() or 'poll' in body_str.lower():
                            print(f"!!! 发现 vote/poll 数据: {url[:80]}")
                            print(json.dumps(body, indent=2, ensure_ascii=False)[:1000])
                except:
                    pass

        page.on("response", handle_response)

        # 访问搜索页
        print("访问搜索页...")
        page.set_default_timeout(60000)
        await page.goto(
            "https://www.xiaohongshu.com/search_result?keyword=帮我选",
            wait_until="domcontentloaded"
        )
        await asyncio.sleep(8)

        print(f"\n捕获到 {len(api_responses)} 个 API 响应")
        for resp in api_responses[:10]:
            print(f"  - {resp['url'][:60]}... status={resp['status']}")
            print(f"    keys: {resp['body_keys']}")

        # 检查页面内容
        print("\n检查页面标题和内容...")
        title = await page.title()
        print(f"页面标题: {title}")

        # 检查是否需要登录
        login_check = await page.evaluate("""() => {
            const loginBtn = document.querySelector('.login-btn, .login-container, [class*="login"]');
            const content = document.body.innerText;
            return {
                hasLoginBtn: !!loginBtn,
                needsLogin: content.includes('登录') && content.includes('注册'),
                bodyPreview: content.slice(0, 300)
            };
        }""")
        print(f"\n登录检查: {login_check}")

        # 截图
        await page.screenshot(path="/app/data/search_check.png")
        print("\n截图保存到: /app/data/search_check.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
