import asyncio
import sys
sys.path.insert(0, '.')
from playwright.async_api import async_playwright

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70e67c433b4bf5d93b8d", "domain": ".xiaohongshu.com", "path": "/"},
]

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()
        page.set_default_timeout(60000)

        await page.goto("https://www.xiaohongshu.com/user/profile/591e353d5e87e752b511b85d", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        result = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state || !state.user) return "no state";

            const upd = state.user.userPageData;
            const pageData = upd._value || upd._rawValue;
            if (!pageData) return "no pageData";

            const basic = pageData.basicInfo || {};

            return {
                basicKeys: Object.keys(basic),
                userId: basic.userId,
                nickname: basic.nickname,
            };
        }""")
        print(result)
        await browser.close()

asyncio.run(test())
