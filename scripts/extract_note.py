import asyncio
import json
from playwright.async_api import async_playwright

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70c195403b4b8a6426a1", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
]

JS_CODE = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state || !state.note || !state.note.noteDetailMap) return null;

    const noteId = Object.keys(state.note.noteDetailMap)[0];
    const detail = state.note.noteDetailMap[noteId];
    if (!detail || !detail.note) return null;

    const n = detail.note;
    const user = n.user || {};
    const interact = n.interactInfo || {};
    const images = n.imageList || [];
    const tags = n.tagList || [];

    return {
        noteId: n.noteId,
        type: n.type,
        title: n.title,
        desc: n.desc,
        time: n.time,
        lastUpdateTime: n.lastUpdateTime,
        ipLocation: n.ipLocation,

        likedCount: interact.likedCount,
        collectedCount: interact.collectedCount,
        commentCount: interact.commentCount,
        shareCount: interact.shareCount,

        userId: user.userId,
        nickname: user.nickname,
        avatar: user.avatar,

        imageCount: images.length,
        images: images.slice(0, 3).map(function(img) {
            return {
                url: img.urlDefault,
                width: img.width,
                height: img.height
            };
        }),

        tags: tags.map(function(t) {
            return {
                id: t.id,
                name: t.name,
                type: t.type
            };
        })
    };
}"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        url = "https://www.xiaohongshu.com/search_result/67556a3a000000000603bf05?xsec_token=ABNMLzBTTm9a9NSniLepgmseumLE2cvaoHgKNceLwXopM=&xsec_source="
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        data = await page.evaluate(JS_CODE)

        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("未找到数据")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
