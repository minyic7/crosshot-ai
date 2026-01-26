"""Test database and image download functionality."""

import asyncio
import sys
sys.path.insert(0, '.')

from datetime import datetime
from apps.database import Database, User, Note, Comment
from apps.crawler.image_downloader import ImageDownloader
from apps.crawler.xhs.scraper import XhsCrawler


async def test_image_download():
    """Test image download using real scraped data."""
    print("=== 测试图片下载 ===")

    # First scrape a real user to get actual URLs
    crawler = XhsCrawler()
    user_id = "591e353d5e87e752b511b85d"
    print(f"抓取用户 {user_id} 获取真实URL...")

    user_info = await crawler.scrape_user(user_id, load_all_notes=False)
    print(f"  昵称: {user_info.nickname}")
    print(f"  头像URL: {user_info.avatar[:80]}...")

    # Now download the avatar
    downloader = ImageDownloader()
    avatar_path = await downloader.download_avatar(user_info.user_id, user_info.avatar)
    print(f"  头像下载: {avatar_path}")

    # Download a note cover if available
    cover_path = None
    if user_info.notes:
        note = user_info.notes[0]
        print(f"  笔记封面URL: {note.cover_url[:80]}...")
        cover_path = await downloader.download_cover(note.note_id, note.cover_url)
        print(f"  封面下载: {cover_path}")

    return avatar_path is not None


async def test_database():
    """Test database operations."""
    print("\n=== 测试数据库 ===")
    db = Database("data/xhs_test.db")
    db.init_db()

    session = db.get_session()

    try:
        # Create a test user
        user = User(
            user_id="test_user_123",
            red_id="test123",
            nickname="测试用户",
            avatar_url="https://example.com/avatar.jpg",
            avatar_path="data/images/avatars/test_user_123.jpg",
            description="这是一个测试用户",
            gender=2,
            ip_location="上海",
            follows_count="100",
            fans_count="1000",
            interaction_count="5000",
        )
        session.merge(user)  # Use merge to handle duplicates
        session.commit()
        print(f"创建用户: {user.nickname}")

        # Create a test note
        note = Note(
            note_id="test_note_123",
            author_user_id="test_user_123",
            title="测试笔记标题",
            content="这是测试笔记的内容",
            note_type="normal",
            likes_count=100,
            cover_url="https://example.com/cover.jpg",
        )
        note.set_image_urls(["https://example.com/1.jpg", "https://example.com/2.jpg"])
        session.merge(note)
        session.commit()
        print(f"创建笔记: {note.title}")

        # Create a test comment
        comment = Comment(
            comment_id="test_comment_123",
            note_id="test_note_123",
            user_id="test_user_123",
            content="这是一条测试评论",
            likes_count=10,
            ip_location="北京",
            create_time=int(datetime.now().timestamp() * 1000),
            created_at=datetime.now(),
        )
        session.merge(comment)
        session.commit()
        print(f"创建评论: {comment.content}")

        # Query back
        saved_user = session.query(User).filter_by(user_id="test_user_123").first()
        saved_note = session.query(Note).filter_by(note_id="test_note_123").first()
        saved_comment = session.query(Comment).filter_by(comment_id="test_comment_123").first()

        print(f"\n查询结果:")
        print(f"  用户: {saved_user.nickname}, 粉丝: {saved_user.fans_count}")
        print(f"  笔记: {saved_note.title}, 图片: {saved_note.get_image_urls()}")
        print(f"  评论: {saved_comment.content}")

        # Test relationship
        print(f"  笔记作者: {saved_note.author.nickname}")
        print(f"  评论所属笔记: {saved_comment.note.title}")

        return True

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        session.close()


async def test_full_scrape():
    """Test full scrape with database and image saving."""
    print("\n=== 测试完整抓取流程 ===")

    db = Database()
    db.init_db()
    downloader = ImageDownloader()
    crawler = XhsCrawler()

    # Scrape user info
    user_id = "591e353d5e87e752b511b85d"
    print(f"抓取用户: {user_id}")

    user_info = await crawler.scrape_user(user_id, load_all_notes=False)
    print(f"  昵称: {user_info.nickname}")
    print(f"  头像URL: {user_info.avatar[:50]}...")

    # Download avatar
    avatar_path = await downloader.download_avatar(user_info.user_id, user_info.avatar)
    print(f"  头像本地路径: {avatar_path}")

    # Save to database
    session = db.get_session()
    try:
        user = User(
            user_id=user_info.user_id,
            red_id=user_info.red_id,
            nickname=user_info.nickname,
            avatar_url=user_info.avatar,
            avatar_path=avatar_path,
            description=user_info.desc,
            gender=user_info.gender,
            ip_location=user_info.ip_location,
            follows_count=user_info.follows,
            fans_count=user_info.fans,
            interaction_count=user_info.interaction,
        )
        session.merge(user)
        session.commit()
        print(f"  已保存到数据库")

        # Verify
        saved = session.query(User).filter_by(user_id=user_id).first()
        print(f"  验证: {saved.nickname}, 头像路径: {saved.avatar_path}")

        return True

    finally:
        session.close()


async def main():
    # Test 1: Image download
    img_ok = await test_image_download()

    # Test 2: Database
    db_ok = await test_database()

    # Test 3: Full scrape (optional, takes longer)
    # full_ok = await test_full_scrape()

    print("\n=== 测试结果 ===")
    print(f"图片下载: {'✓' if img_ok else '✗'}")
    print(f"数据库: {'✓' if db_ok else '✗'}")
    # print(f"完整抓取: {'✓' if full_ok else '✗'}")


if __name__ == "__main__":
    asyncio.run(main())
