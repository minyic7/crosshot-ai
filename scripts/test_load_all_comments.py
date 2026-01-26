import asyncio
import json
from datetime import datetime
from apps.crawler.xhs.scraper import XhsCrawler


async def main():
    crawler = XhsCrawler()

    # 搜索笔记
    print("搜索笔记...")
    async with crawler:
        notes = await crawler.scrape("melbourne")

    print(f"找到 {len(notes)} 篇笔记")

    # 选第二个笔记（有更多评论）
    note = notes[1] if len(notes) > 1 else notes[0]
    print(f"\n笔记: {note.title}")
    print(f"URL: {note.note_url[:70]}...")

    # 测试1: 只获取初始评论
    print("\n=== 测试1: 初始评论 (load_all=False) ===")
    comments1 = await crawler.scrape_comments(note.note_url, load_all=False)
    print(f"评论数: {len(comments1)}")

    # 测试2: 加载全部评论
    print("\n=== 测试2: 全部评论 (load_all=True) ===")
    comments2 = await crawler.scrape_comments(note.note_url, load_all=True)
    print(f"评论数: {len(comments2)}")

    # 显示所有评论
    print("\n=== 全部评论 ===")
    for i, c in enumerate(comments2, 1):
        time_str = datetime.fromtimestamp(c.create_time / 1000).strftime("%Y-%m-%d") if c.create_time else ""
        print(f"{i}. [{c.ip_location or '?'}] {c.nickname}: {c.content[:40]}... ({time_str})")

        # 显示子评论
        for sc in c.sub_comments:
            print(f"   └─ {sc.nickname}: {sc.content[:30]}...")

    # 统计
    total_sub = sum(len(c.sub_comments) for c in comments2)
    print(f"\n总计: {len(comments2)} 条主评论, {total_sub} 条已加载的子评论")


if __name__ == "__main__":
    asyncio.run(main())
