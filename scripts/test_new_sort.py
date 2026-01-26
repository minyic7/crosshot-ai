"""Test the new sort functionality in XhsCrawler."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.crawler.xhs.scraper import XhsCrawler, SortBy, NoteType


async def test_new_sort():
    """Test different sort options."""

    keyword = "melbourne"

    print("=" * 60)
    print("测试 XhsCrawler 排序功能")
    print("=" * 60)

    async with XhsCrawler() as crawler:
        # Test 1: Default (综合)
        print("\n\n" + "-" * 40)
        print("测试1: 默认排序 (综合)")
        print("-" * 40)

        notes = await crawler.scrape(
            keyword,
            sort_by=SortBy.GENERAL,
            max_notes=5,
            scroll_count=1
        )

        print(f"\n获取到 {len(notes)} 条笔记:")
        for i, note in enumerate(notes, 1):
            print(f"  {i}. {note.title[:30]}... (点赞: {note.likes})")

        # Clear seen URLs for next test
        crawler._seen_note_urls.clear()

        # Test 2: 最新
        print("\n\n" + "-" * 40)
        print("测试2: 最新排序")
        print("-" * 40)

        notes = await crawler.scrape(
            keyword,
            sort_by=SortBy.NEWEST,
            max_notes=5,
            scroll_count=1
        )

        print(f"\n获取到 {len(notes)} 条笔记:")
        for i, note in enumerate(notes, 1):
            print(f"  {i}. {note.title[:30]}... (点赞: {note.likes})")

        # Clear for next test
        crawler._seen_note_urls.clear()

        # Test 3: 最多点赞
        print("\n\n" + "-" * 40)
        print("测试3: 最多点赞排序")
        print("-" * 40)

        notes = await crawler.scrape(
            keyword,
            sort_by=SortBy.MOST_LIKED,
            max_notes=5,
            scroll_count=1
        )

        print(f"\n获取到 {len(notes)} 条笔记:")
        for i, note in enumerate(notes, 1):
            print(f"  {i}. {note.title[:30]}... (点赞: {note.likes})")

    print("\n\n测试完成!")


if __name__ == "__main__":
    asyncio.run(test_new_sort())
