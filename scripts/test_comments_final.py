import asyncio
import json
from datetime import datetime
from apps.crawler.xhs.scraper import XhsCrawler


async def main():
    crawler = XhsCrawler()

    # 先搜索获取笔记
    print("搜索笔记...")
    async with crawler:
        notes = await crawler.scrape("melbourne")

    if not notes:
        print("未找到笔记")
        return

    print(f"找到 {len(notes)} 篇笔记")

    # 显示所有笔记
    print("\n笔记列表:")
    for i, n in enumerate(notes):
        print(f"  {i+1}. {n.title[:30]}... - {n.note_url[:50] if n.note_url else 'no url'}...")

    # 取第二个有URL的笔记（第一个通常没评论）
    note = None
    count = 0
    for n in notes:
        if n.note_url:
            count += 1
            if count >= 2:  # 取第2个
                note = n
                break

    if not note:
        print("没有可用的笔记URL")
        return

    print(f"\n抓取评论: {note.title}")
    print(f"URL: {note.note_url[:80]}...")

    # 抓取评论
    comments = await crawler.scrape_comments(note.note_url, scroll_times=3)

    print(f"\n找到 {len(comments)} 条评论:")
    print("=" * 60)

    for i, c in enumerate(comments[:10], 1):
        # 转换时间戳
        time_str = ""
        if c.create_time:
            try:
                time_str = datetime.fromtimestamp(c.create_time / 1000).strftime("%Y-%m-%d %H:%M")
            except:
                time_str = str(c.create_time)

        print(f"\n{i}. {c.nickname} ({c.ip_location or '未知'})")
        print(f"   {c.content}")
        print(f"   👍 {c.likes} | 时间: {time_str} | 回复数: {c.sub_comment_count}")

        # 显示子评论
        if c.sub_comments:
            for sc in c.sub_comments[:2]:
                sc_time = ""
                if sc.create_time:
                    try:
                        sc_time = datetime.fromtimestamp(sc.create_time / 1000).strftime("%Y-%m-%d %H:%M")
                    except:
                        sc_time = str(sc.create_time)
                print(f"   └─ {sc.nickname}: {sc.content[:50]}... ({sc_time})")

    # 保存到文件
    output = {
        "note": {
            "title": note.title,
            "url": note.note_url,
        },
        "comments": [c.model_dump() for c in comments],
    }

    with open("/app/data/comments_sample.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n\n评论数据已保存到 /app/data/comments_sample.json")


if __name__ == "__main__":
    asyncio.run(main())
