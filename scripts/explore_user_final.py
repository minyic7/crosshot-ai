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

        user_id = "591e353d5e87e752b511b85d"
        user_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        print(f"访问用户主页: {user_url}")
        await page.goto(user_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 完整提取用户信息
        result = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state?.user) return { error: 'no user state' };

            // 获取 userPageData
            const pageData = state.user.userPageData?._value || state.user.userPageData?._rawValue;
            if (!pageData) return { error: 'no pageData' };

            const basic = pageData.basicInfo || {};
            const interactions = pageData.interactions || [];

            // 用户基本信息
            const userInfo = {
                nickname: basic.nickname,
                avatar: basic.images || basic.imageb,
                desc: basic.desc,
                gender: basic.gender,  // 0=未知, 1=男, 2=女
                ipLocation: basic.ipLocation,
                redId: basic.redId,
            };

            // 互动数据
            const stats = {};
            for (const item of interactions) {
                stats[item.type] = item.count;
            }

            // 获取笔记
            const notesRef = state.user.notes;
            const notesArray = notesRef?._value || notesRef?._rawValue || [];

            const notes = [];
            for (const item of notesArray) {
                // 每个 item 是数组，第一个元素包含 noteCard
                if (Array.isArray(item) && item[0]?.noteCard) {
                    const card = item[0].noteCard;
                    notes.push({
                        noteId: card.noteId,
                        title: card.displayTitle,
                        type: card.type,
                        likedCount: card.interactInfo?.likedCount,
                        cover: card.cover?.urlDefault,
                        xsecToken: card.xsecToken,
                    });
                }
            }

            return {
                userInfo,
                stats,
                notesCount: notes.length,
                notes: notes.slice(0, 10),
            };
        }""")

        # 补充 userId（JS里访问不到）
        if result.get('userInfo'):
            result['userInfo']['userId'] = user_id

        print(json.dumps(result, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
