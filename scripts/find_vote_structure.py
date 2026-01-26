import asyncio
from playwright.async_api import async_playwright
import json

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70c195403b4b8a6426a1", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
]

# 检查 __INITIAL_STATE__ 中是否有 vote/poll 相关字段
JS_CHECK_VOTE_FIELDS = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state) return {error: 'no state'};

    // 递归搜索对象中包含 vote/poll/pk 的键
    function findVoteKeys(obj, path = '', results = []) {
        if (!obj || typeof obj !== 'object') return results;

        for (const key of Object.keys(obj)) {
            const newPath = path ? `${path}.${key}` : key;
            const lowerKey = key.toLowerCase();

            if (lowerKey.includes('vote') || lowerKey.includes('poll') ||
                lowerKey.includes('pk') || lowerKey.includes('option') ||
                lowerKey.includes('choice') || lowerKey.includes('survey')) {
                results.push({path: newPath, key: key, value: typeof obj[key]});
            }

            if (typeof obj[key] === 'object' && obj[key] !== null && results.length < 50) {
                findVoteKeys(obj[key], newPath, results);
            }
        }
        return results;
    }

    return findVoteKeys(state);
}"""

# 检查笔记详情中的 interactInfo 和其他可能包含投票的字段
JS_CHECK_NOTE_INTERACT = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state || !state.note || !state.note.noteDetailMap) return null;

    const noteId = Object.keys(state.note.noteDetailMap)[0];
    if (!noteId) return null;

    const detail = state.note.noteDetailMap[noteId];
    if (!detail || !detail.note) return null;

    const n = detail.note;

    // 返回可能与投票相关的所有字段
    return {
        noteId: n.noteId,
        type: n.type,
        title: n.title,
        // 检查 interactInfo
        interactInfo: n.interactInfo,
        // 检查是否有 vote 相关
        vote: n.vote,
        poll: n.poll,
        // 检查 noteCard 或其他嵌套对象
        noteCard: n.noteCard ? Object.keys(n.noteCard) : null,
        // 获取所有顶级键
        allKeys: Object.keys(n),
        // 检查 desc 中是否有选项文本
        descPreview: n.desc ? n.desc.slice(0, 200) : null,
    };
}"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        # 搜索可能有投票的笔记
        keywords = ["帮我选一个", "投票选择", "你们选哪个"]

        for keyword in keywords:
            print(f"\n{'='*60}")
            print(f"搜索: {keyword}")
            print('='*60)

            await page.goto(
                f"https://www.xiaohongshu.com/search_result?keyword={keyword}",
                wait_until="domcontentloaded"
            )
            await asyncio.sleep(5)

            # 检查搜索结果页面的 state 中是否有 vote 相关字段
            vote_fields = await page.evaluate(JS_CHECK_VOTE_FIELDS)
            if vote_fields and isinstance(vote_fields, list) and len(vote_fields) > 0:
                print(f"发现 vote/poll 相关字段: {len(vote_fields)}")
                for item in vote_fields[:10]:
                    print(f"  - {item['path']}: {item['value']}")
            elif vote_fields:
                print(f"vote_fields 结果: {vote_fields}")
            else:
                print("搜索结果页未发现 vote/poll 相关字段")

            # 获取搜索结果中的笔记链接
            links = await page.evaluate("""() => {
                const cards = document.querySelectorAll('section.note-item a.cover');
                return Array.from(cards).slice(0, 3).map(a => {
                    const href = a.getAttribute('href');
                    if (href && href.startsWith('/')) {
                        return 'https://www.xiaohongshu.com' + href;
                    }
                    return href;
                }).filter(Boolean);
            }""")

            print(f"\n找到 {len(links)} 个笔记链接")

            # 访问每个笔记详情页
            for i, link in enumerate(links[:2]):
                print(f"\n--- 笔记 {i+1}: {link[:60]}... ---")
                await page.goto(link, wait_until="domcontentloaded")
                await asyncio.sleep(4)

                # 检查笔记详情
                note_info = await page.evaluate(JS_CHECK_NOTE_INTERACT)
                if note_info:
                    print(f"type: {note_info.get('type')}")
                    print(f"title: {note_info.get('title', '')[:50]}")
                    print(f"interactInfo: {note_info.get('interactInfo')}")
                    print(f"vote: {note_info.get('vote')}")
                    print(f"poll: {note_info.get('poll')}")
                    print(f"allKeys: {note_info.get('allKeys')}")

                    # 检查 vote 相关字段
                    vote_fields_detail = await page.evaluate(JS_CHECK_VOTE_FIELDS)
                    if vote_fields_detail and isinstance(vote_fields_detail, list):
                        vote_related = [v for v in vote_fields_detail if 'note' in v['path'].lower()]
                        if vote_related:
                            print(f"笔记中的 vote 相关字段: {vote_related}")
                else:
                    print("未能获取笔记详情")

        await browser.close()
        print("\n" + "="*60)
        print("搜索完成")


if __name__ == "__main__":
    asyncio.run(main())
