import asyncio
from playwright.async_api import async_playwright
import json

COOKIES = [
    {"name": "a1", "value": "19be03c659208ir92xgk035nag8mz779vmahahts230000849201", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b0b46a1812aa70c195403b4b8a6426a1", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "8409f207a38cc6017a2e3af122fd9261", "domain": ".xiaohongshu.com", "path": "/"},
]

JS_GET_ALL_FIELDS = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state || !state.note || !state.note.noteDetailMap) return null;
    const noteId = Object.keys(state.note.noteDetailMap)[0];
    const detail = state.note.noteDetailMap[noteId];
    if (!detail || !detail.note) return null;

    // 返回完整的 note 对象的所有字段名和值类型
    const n = detail.note;
    const result = {};
    for (const key of Object.keys(n)) {
        const val = n[key];
        result[key] = {
            type: typeof val,
            isArray: Array.isArray(val),
            isNull: val === null,
            sample: typeof val === 'object' && val !== null ?
                    (Array.isArray(val) ? val.length + ' items' : Object.keys(val).slice(0,5).join(',')) :
                    String(val).slice(0, 50)
        };
    }
    return result;
}"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        # 访问一篇笔记
        url = "https://www.xiaohongshu.com/search_result/67556a3a000000000603bf05?xsec_token=ABNMLzBTTm9a9NSniLepgmseumLE2cvaoHgKNceLwXopM=&xsec_source="
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        fields = await page.evaluate(JS_GET_ALL_FIELDS)

        if fields:
            print("=" * 60)
            print("笔记对象的所有字段:")
            print("=" * 60)
            for key, info in sorted(fields.items()):
                print(f"{key}:")
                print(f"  type: {info['type']}, isArray: {info['isArray']}, isNull: {info['isNull']}")
                print(f"  sample: {info['sample']}")
                print()
        else:
            print("未获取到数据")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
