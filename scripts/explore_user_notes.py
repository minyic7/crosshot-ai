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

        # 深入探索 notes 结构
        notes_structure = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const notesRef = state?.user?.notes;
            if (!notesRef) return { error: 'no notes ref' };

            // 获取实际值
            const notes = notesRef._value || notesRef._rawValue;
            if (!notes) return { error: 'no notes value', refKeys: Object.keys(notesRef) };

            // 检查 notes 的结构
            const result = {
                type: typeof notes,
                isArray: Array.isArray(notes),
            };

            if (Array.isArray(notes)) {
                result.length = notes.length;
                if (notes[0]) {
                    // 检查第一个元素
                    const first = notes[0];
                    if (first._value) {
                        result.firstValueKeys = Object.keys(first._value);
                        result.firstValue = first._value;
                    } else {
                        result.firstKeys = Object.keys(first);
                        result.first = first;
                    }
                }
            } else {
                result.keys = Object.keys(notes).slice(0, 10);
            }

            return result;
        }""")

        print(f"\nnotes 结构:")
        print(json.dumps(notes_structure, indent=2, ensure_ascii=False, default=str)[:2000])

        # 尝试直接获取笔记数组
        notes_data = await page.evaluate("""() => {
            const state = window.__INITIAL_STATE__;
            const notesRef = state?.user?.notes;
            if (!notesRef) return null;

            const notes = notesRef._value || notesRef._rawValue || [];

            // notes 是数组，但每个元素可能也是 Vue ref
            return notes.slice(0, 5).map((noteRef, i) => {
                // 获取实际的 note 对象
                const note = noteRef?._value || noteRef?._rawValue || noteRef;
                if (!note || typeof note !== 'object') return { index: i, error: 'not object' };

                return {
                    noteId: note.noteId || note.id,
                    displayTitle: note.displayTitle,
                    type: note.type,
                    likedCount: note.interactInfo?.likedCount,
                    cover: note.cover?.urlDefault || note.cover?.url,
                    xsecToken: note.xsecToken,
                    // 所有字段
                    keys: Object.keys(note).slice(0, 15),
                };
            });
        }""")

        print(f"\n笔记数据:")
        print(json.dumps(notes_data, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
