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

        # 使用 _value 访问实际数据
        user_info = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state?.user) return { error: 'no user' };

            // 获取 userPageData 的实际值
            const pageData = state.user.userPageData?._value || state.user.userPageData?._rawValue;
            if (!pageData) return { error: 'no pageData value' };

            const basic = pageData.basicInfo;
            const interactions = pageData.interactions;

            return {
                // 基本信息
                userId: basic?.userId,
                nickname: basic?.nickname,
                avatar: basic?.images,  // 头像URL
                desc: basic?.desc,       // 简介
                gender: basic?.gender,   // 0=未知, 1=男, 2=女
                ipLocation: basic?.ipLocation,
                redId: basic?.redId,     // 小红书号

                // 互动数据
                interactions: interactions,

                // basicInfo 所有字段
                basicInfoKeys: basic ? Object.keys(basic) : null,
            };
        }""")

        print(f"\n用户信息:")
        print(json.dumps(user_info, indent=2, ensure_ascii=False))

        # 获取笔记列表
        notes_list = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state?.user?.notes) return { error: 'no notes' };

            // 获取 notes 的实际值
            const notes = state.user.notes._value || state.user.notes._rawValue || state.user.notes;

            if (!notes || typeof notes !== 'object') return { error: 'notes not object' };

            // notes 可能是数组或对象
            let noteArray;
            if (Array.isArray(notes)) {
                noteArray = notes;
            } else {
                noteArray = Object.values(notes).filter(n => n && typeof n === 'object' && n.noteId);
            }

            return {
                count: noteArray.length,
                notes: noteArray.slice(0, 5).map(n => ({
                    noteId: n.noteId,
                    title: n.displayTitle || n.title,
                    type: n.type,
                    likedCount: n.interactInfo?.likedCount,
                    cover: n.cover?.urlDefault,
                    xsecToken: n.xsecToken,
                }))
            };
        }""")

        print(f"\n用户笔记:")
        print(json.dumps(notes_list, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
