import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70c195403b4b8a6426a1", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        # 搜索 "pk" 或 "投票功能"
        keywords = ["pk投票", "小红书投票功能", "投票器"]

        for keyword in keywords:
            print(f"\n=== 搜索: {keyword} ===")
            await page.goto(f"https://www.xiaohongshu.com/search_result?keyword={keyword}", wait_until="domcontentloaded")
            await asyncio.sleep(5)

            links = await page.evaluate(
                """() => {
                const cards = document.querySelectorAll('section.note-item a[href*="search_result/"]');
                return Array.from(cards).slice(0, 8).map(a => a.href);
            }"""
            )

            for i, link in enumerate(links):
                await page.goto(link, wait_until="domcontentloaded")
                await asyncio.sleep(4)

                title = await page.title()
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                # 找所有 class 包含 vote/poll/pk 的元素
                vote_elements = soup.select('[class*="vote"], [class*="poll"], [class*="pk"]')

                # 找 button 或可点击的选项
                buttons = soup.select('button, [role="button"]')

                print(f"{i+1}. {title[:40]}...")
                if vote_elements:
                    print(f"   找到 vote/poll/pk 元素: {len(vote_elements)}")
                    for el in vote_elements[:3]:
                        print(f"   - {el.name}.{el.get('class')}")

                # 检查是否有投票相关的文本模式
                if re.search(r"(选项|选择|投票|pk|vs)", html, re.IGNORECASE):
                    # 查找可能的投票选项结构
                    options = soup.select(".option, .choice, .vote-item, .pk-item")
                    if options:
                        print(f"   找到选项元素: {len(options)}")

        # 尝试直接搜索带 pk 功能的笔记
        print("\n=== 搜索带互动功能的笔记 ===")
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=帮我选 投票结果", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        html = await page.content()

        # 截图看看搜索结果
        await page.screenshot(path="/app/search_poll.png")
        print("搜索结果截图: /app/search_poll.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
