"""Test complete scrape -> download images -> save to database pipeline."""

import asyncio
import sys
import time
sys.path.insert(0, '.')

from apps.crawler.xhs.scraper import XhsCrawler
from apps.services.data_service import DataService


async def test_full_pipeline():
    """Test the complete data pipeline."""
    print("=" * 60)
    print("测试完整数据管道: 抓取 -> 下载图片 -> 保存数据库")
    print("=" * 60)

    crawler = XhsCrawler()
    service = DataService()

    # ==================== 1. 搜索笔记 ====================
    print("\n[1/4] 搜索笔记...")
    start = time.time()
    try:
        notes = await crawler.scrape("melbourne")
    except Exception as e:
        print(f"  搜索出错: {e}")
        import traceback
        traceback.print_exc()
        notes = []
    duration = int((time.time() - start) * 1000)
    print(f"  找到 {len(notes)} 篇笔记 ({duration}ms)")

    if not notes:
        print("  未找到笔记，退出")
        return

    # 保存笔记到数据库
    print(f"  保存笔记到数据库...")
    for note in notes[:3]:  # Only save first 3 for testing
        try:
            saved_note = await service.save_note(note, download_images=True)
            print(f"    ✓ {saved_note.title[:30]}...")
        except Exception as e:
            print(f"    ✗ 保存失败: {e}")

    service.log_scrape("search", "melbourne", items_count=len(notes), duration_ms=duration)

    # ==================== 2. 获取用户信息 ====================
    print("\n[2/4] 获取用户信息...")
    user_id = "591e353d5e87e752b511b85d"  # Test user
    start = time.time()
    user_info = await crawler.scrape_user(user_id, load_all_notes=False)
    duration = int((time.time() - start) * 1000)

    if user_info.nickname:
        print(f"  用户: {user_info.nickname}")
        print(f"  粉丝: {user_info.fans}, 获赞: {user_info.interaction}")
        print(f"  笔记数: {len(user_info.notes)}")

        # 保存用户到数据库
        print(f"  保存用户到数据库...")
        try:
            saved_user = await service.save_user(user_info, download_avatar=True)
            print(f"    ✓ 用户 {saved_user.nickname} 已保存")
            print(f"    头像: {saved_user.avatar_path}")
        except Exception as e:
            print(f"    ✗ 保存失败: {e}")

        service.log_scrape("user", user_id, items_count=1, duration_ms=duration)
    else:
        print(f"  未获取到用户信息 ({duration}ms)")

    # ==================== 3. 获取笔记评论 ====================
    print("\n[3/4] 获取笔记评论...")
    if notes:
        note = notes[0]
        start = time.time()
        comments = await crawler.scrape_comments(note.note_url, load_all=True, expand_sub_comments=True)
        duration = int((time.time() - start) * 1000)

        total_sub = sum(len(c.sub_comments) for c in comments)
        print(f"  主评论: {len(comments)}, 子评论: {total_sub} ({duration}ms)")

        # 保存评论到数据库
        if comments:
            print(f"  保存评论到数据库...")
            note_id = service._extract_note_id(note.note_url)
            if note_id:
                try:
                    saved_comments = await service.save_comments(
                        note_id, comments, download_avatars=True
                    )
                    print(f"    ✓ 保存 {len(saved_comments)} 条评论")
                except Exception as e:
                    print(f"    ✗ 保存失败: {e}")

                service.log_scrape("comments", note_id, items_count=len(comments), duration_ms=duration)

    # ==================== 4. 验证数据库 ====================
    print("\n[4/4] 验证数据库...")
    session = service.get_session()
    try:
        from apps.database import User, Note, Comment, ScrapeLog

        user_count = session.query(User).count()
        note_count = session.query(Note).count()
        comment_count = session.query(Comment).count()
        log_count = session.query(ScrapeLog).count()

        print(f"  用户: {user_count}")
        print(f"  笔记: {note_count}")
        print(f"  评论: {comment_count}")
        print(f"  日志: {log_count}")

        # Show sample data
        print("\n  示例数据:")
        sample_user = session.query(User).first()
        if sample_user:
            print(f"    用户: {sample_user.nickname} ({sample_user.user_id[:12]}...)")
            print(f"    头像: {sample_user.avatar_path or '未下载'}")

        sample_note = session.query(Note).first()
        if sample_note:
            print(f"    笔记: {sample_note.title[:30]}...")
            print(f"    封面: {sample_note.cover_path or '未下载'}")

    finally:
        session.close()

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
