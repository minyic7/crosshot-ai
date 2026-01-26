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

    note = notes[1] if len(notes) > 1 else notes[0]
    print(f"笔记: {note.title}")
    print(f"URL: {note.note_url[:70]}...")

    # 测试1: 不展开子评论
    print("\n=== 测试1: 不展开子评论 ===")
    comments1 = await crawler.scrape_comments(note.note_url, load_all=True, expand_sub_comments=False)
    sub_count1 = sum(len(c.sub_comments) for c in comments1)
    print(f"主评论: {len(comments1)}, 子评论: {sub_count1}")

    # 测试2: 展开子评论
    print("\n=== 测试2: 展开子评论 ===")
    comments2 = await crawler.scrape_comments(note.note_url, load_all=True, expand_sub_comments=True)
    sub_count2 = sum(len(c.sub_comments) for c in comments2)
    print(f"主评论: {len(comments2)}, 子评论: {sub_count2}")

    # 对比
    print(f"\n子评论增加: {sub_count2 - sub_count1} 条")

    # 显示有子评论的评论
    print("\n=== 有子评论的评论 ===")
    for c in comments2:
        if c.sub_comments:
            print(f"\n{c.nickname}: {c.content[:30]}...")
            print(f"  声明有 {c.sub_comment_count} 条回复, 实际加载 {len(c.sub_comments)} 条")
            for sc in c.sub_comments[:5]:
                print(f"  └─ {sc.nickname}: {sc.content[:25]}...")
            if len(c.sub_comments) > 5:
                print(f"  └─ ... 还有 {len(c.sub_comments) - 5} 条")


if __name__ == "__main__":
    asyncio.run(main())
