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

        # 检查 user 下的所有字段
        user_structure = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            if (!state?.user) return { error: 'no user' };

            const user = state.user;
            const result = {};

            for (const key of Object.keys(user)) {
                const val = user[key];
                if (val === null || val === undefined) {
                    result[key] = 'null';
                } else if (typeof val === 'object') {
                    if (Array.isArray(val)) {
                        result[key] = `array(${val.length})`;
                    } else {
                        result[key] = `object(${Object.keys(val).slice(0, 5).join(',')})`;
                    }
                } else {
                    result[key] = typeof val;
                }
            }
            return result;
        }""")

        print(f"\nuser 结构:")
        print(json.dumps(user_structure, indent=2))

        # 检查 userPageData 的结构
        page_data = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const data = state?.user?.userPageData;
            if (!data) return { error: 'no userPageData' };

            const result = {};
            for (const key of Object.keys(data)) {
                const val = data[key];
                if (val === null || val === undefined) {
                    result[key] = 'null';
                } else if (typeof val === 'object') {
                    if (Array.isArray(val)) {
                        result[key] = `array(${val.length})`;
                    } else {
                        result[key] = `object(${Object.keys(val).slice(0, 8).join(',')})`;
                    }
                } else {
                    result[key] = typeof val;
                }
            }
            return result;
        }""")

        print(f"\nuserPageData 结构:")
        print(json.dumps(page_data, indent=2))

        # 检查 basicInfo
        basic_info = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const basic = state?.user?.userPageData?.basicInfo;
            if (!basic) return { error: 'no basicInfo' };

            return {
                keys: Object.keys(basic),
            };
        }""")

        print(f"\nbasicInfo keys: {basic_info}")

        # 获取完整的 basicInfo
        basic_full = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const basic = state?.user?.userPageData?.basicInfo;
            if (!basic) return null;

            return {
                userId: basic.userId,
                nickname: basic.nickname,
                images: basic.images,  // 头像
                desc: basic.desc,
                gender: basic.gender,
                ipLocation: basic.ipLocation,
                redId: basic.redId,
                // 可能还有其他字段
                fansCount: basic.fansCount,
                follows: basic.follows,
            };
        }""")

        print(f"\nbasicInfo 详情:")
        print(json.dumps(basic_full, indent=2, ensure_ascii=False))

        # 获取 interactions
        interactions = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const inter = state?.user?.userPageData?.interactions;
            if (!inter) return null;
            return inter;
        }""")

        print(f"\ninteractions:")
        print(json.dumps(interactions, indent=2, ensure_ascii=False))

        # 获取笔记
        notes_info = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const notes = state?.user?.notes;
            if (!notes) return { error: 'no notes' };

            // notes 可能是对象而不是数组
            const noteIds = Object.keys(notes);
            const firstNoteId = noteIds[0];
            const firstNote = notes[firstNoteId];

            return {
                type: typeof notes,
                isArray: Array.isArray(notes),
                noteCount: noteIds.length,
                noteIds: noteIds.slice(0, 5),
                firstNoteKeys: firstNote ? Object.keys(firstNote) : null,
            };
        }""")

        print(f"\nnotes 结构:")
        print(json.dumps(notes_info, indent=2))

        # 获取第一个笔记详情
        first_note = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const notes = state?.user?.notes;
            if (!notes) return null;

            const noteIds = Object.keys(notes);
            if (noteIds.length === 0) return null;

            const note = notes[noteIds[0]];
            return {
                noteId: note.noteId,
                title: note.displayTitle,
                type: note.type,
                likedCount: note.interactInfo?.likedCount,
                cover: note.cover?.urlDefault,
                xsecToken: note.xsecToken,
            };
        }""")

        print(f"\n第一个笔记:")
        print(json.dumps(first_note, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
