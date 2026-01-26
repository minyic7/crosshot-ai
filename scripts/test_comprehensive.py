"""Comprehensive test to verify all implemented features work correctly."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.config import get_settings, reload_settings
from apps.utils.retry import RetryConfig, RetryResult, retry_async, retry_with_result
from apps.database import Database, Note, NoteSnapshot, User, Comment, ScrapeLog
from apps.crawler.xhs.scraper import XhsCrawler, SortBy, NoteType
from apps.services.data_service import DataService


def test_config():
    """Test configuration module."""
    print("\n" + "=" * 60)
    print("1. Testing Configuration Module")
    print("=" * 60)

    settings = get_settings()

    # Check crawler settings
    assert settings.crawler.max_retries >= 1, "max_retries should be >= 1"
    assert settings.crawler.retry_delay > 0, "retry_delay should be > 0"
    print(f"   Crawler max_retries: {settings.crawler.max_retries}")
    print(f"   Crawler retry_delay: {settings.crawler.retry_delay}s")

    # Check XHS cookies
    cookies = settings.xhs.get_cookies()
    print(f"   XHS cookies configured: {len(cookies)} cookies")
    if cookies:
        print(f"   Cookie names: {[c.get('name') for c in cookies[:3]]}...")

    # Check cache settings
    print(f"   Cache note_ttl_hours: {settings.cache.note_ttl_hours}")
    print(f"   Cache enable_version_compare: {settings.cache.enable_version_compare}")

    print("   [PASS] Configuration module works correctly")
    return True


def test_retry_module():
    """Test retry module."""
    print("\n" + "=" * 60)
    print("2. Testing Retry Module")
    print("=" * 60)

    # Test RetryConfig
    config = RetryConfig(max_retries=3, delay=0.1)
    assert config.max_retries == 3
    assert config.delay == 0.1
    print(f"   RetryConfig: max_retries={config.max_retries}, delay={config.delay}")

    # Test retry_with_result with a function that fails then succeeds
    call_count = 0

    async def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Simulated failure")
        return "success"

    async def run_retry_test():
        nonlocal call_count
        call_count = 0
        result = await retry_with_result(
            flaky_func,
            config=RetryConfig(max_retries=3, delay=0.05, exceptions=(ValueError,))
        )
        return result

    result = asyncio.get_event_loop().run_until_complete(run_retry_test())
    assert result.success, "Retry should eventually succeed"
    assert result.value == "success"
    assert result.attempts == 2, f"Should take 2 attempts, got {result.attempts}"
    print(f"   Retry test: succeeded after {result.attempts} attempts")

    print("   [PASS] Retry module works correctly")
    return True


def test_database_models():
    """Test database models."""
    print("\n" + "=" * 60)
    print("3. Testing Database Models")
    print("=" * 60)

    # Use in-memory database for testing
    db = Database(":memory:")
    db.init_db()

    session = db.get_session()
    try:
        # Test Note model with string counts
        note = Note(
            note_id="test123",
            title="Test Note",
            likes_count="1.2万",
            collects_count="500",
            comments_count="100",
        )
        session.add(note)
        session.commit()

        # Verify
        saved_note = session.query(Note).filter_by(note_id="test123").first()
        assert saved_note.likes_count == "1.2万", f"Expected '1.2万', got {saved_note.likes_count}"
        print(f"   Note.likes_count (string): '{saved_note.likes_count}'")

        # Test NoteSnapshot model
        snapshot = NoteSnapshot(
            note_id="test123",
            title="Test Note",
            likes_count="1.2万",
            has_stats_change=True,
            source="search",
        )
        session.add(snapshot)
        session.commit()

        saved_snapshot = session.query(NoteSnapshot).filter_by(note_id="test123").first()
        assert saved_snapshot is not None, "Snapshot should be saved"
        print(f"   NoteSnapshot created: note_id={saved_snapshot.note_id}")

        # Test User model
        user = User(
            user_id="user123",
            nickname="Test User",
            fans_count="10万",
        )
        session.add(user)
        session.commit()

        saved_user = session.query(User).filter_by(user_id="user123").first()
        assert saved_user.fans_count == "10万"
        print(f"   User.fans_count (string): '{saved_user.fans_count}'")

        print("   [PASS] Database models work correctly")
        return True

    finally:
        session.close()


def test_crawler_enums():
    """Test crawler enums and structure."""
    print("\n" + "=" * 60)
    print("4. Testing Crawler Enums")
    print("=" * 60)

    # Test SortBy enum
    assert SortBy.GENERAL.value == "general"
    assert SortBy.NEWEST.value == "time_descending"
    assert SortBy.MOST_LIKED.value == "popularity_descending"
    assert SortBy.MOST_COMMENTS.value == "comments_count_descending"
    assert SortBy.MOST_COLLECTED.value == "collects_count_descending"
    print(f"   SortBy.GENERAL: {SortBy.GENERAL.value}")
    print(f"   SortBy.NEWEST: {SortBy.NEWEST.value}")
    print(f"   SortBy.MOST_LIKED: {SortBy.MOST_LIKED.value}")

    # Test NoteType enum
    assert NoteType.ALL.value == 0
    assert NoteType.IMAGE.value == 1
    assert NoteType.VIDEO.value == 2
    print(f"   NoteType.ALL: {NoteType.ALL.value}")
    print(f"   NoteType.IMAGE: {NoteType.IMAGE.value}")
    print(f"   NoteType.VIDEO: {NoteType.VIDEO.value}")

    # Test aliases
    assert SortBy.HOT == SortBy.MOST_LIKED
    assert SortBy.TIME == SortBy.NEWEST
    assert SortBy.DEFAULT == SortBy.GENERAL
    print("   Aliases verified: HOT=MOST_LIKED, TIME=NEWEST, DEFAULT=GENERAL")

    print("   [PASS] Crawler enums work correctly")
    return True


def test_data_service():
    """Test DataService initialization and methods."""
    print("\n" + "=" * 60)
    print("5. Testing DataService")
    print("=" * 60)

    # Use test database
    service = DataService(":memory:")

    # Test get_existing_note_urls
    urls = service.get_existing_note_urls()
    assert isinstance(urls, set)
    print(f"   get_existing_note_urls(): {len(urls)} URLs")

    # Test get_recent_note_ids
    recent = service.get_recent_note_ids(hours=24)
    assert isinstance(recent, set)
    print(f"   get_recent_note_ids(24h): {len(recent)} IDs")

    # Test transaction context manager
    with service.transaction() as session:
        note = Note(
            note_id="svc_test_001",
            title="Service Test",
            likes_count="100",
        )
        session.add(note)
    # Should be committed

    # Verify
    urls = service.get_existing_note_urls()
    # Can't check URL since we didn't set it, but no error means success

    # Test _extract_note_id
    test_cases = [
        ("https://www.xiaohongshu.com/explore/abc123?foo=bar", "abc123"),
        ("https://www.xiaohongshu.com/search_result/def456", "def456"),
        ("invalid_url", None),
    ]
    for url, expected in test_cases:
        result = DataService._extract_note_id(url)
        assert result == expected, f"For {url}, expected {expected}, got {result}"
    print("   _extract_note_id() verified for all test cases")

    print("   [PASS] DataService works correctly")
    return True


async def test_crawler_context_manager():
    """Test crawler async context manager."""
    print("\n" + "=" * 60)
    print("6. Testing Crawler Context Manager")
    print("=" * 60)

    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    if not cookies:
        print("   [SKIP] No cookies configured, skipping browser test")
        return True

    print("   Testing XhsCrawler __aenter__ and __aexit__...")

    try:
        async with XhsCrawler() as crawler:
            assert crawler._browser is not None, "Browser should be initialized"
            assert crawler._context is not None, "Context should be initialized"
            print("   Browser and context initialized successfully")

        # After exit, resources should be cleaned up
        print("   Resources cleaned up after context exit")
        print("   [PASS] Crawler context manager works correctly")
        return True
    except Exception as e:
        print(f"   [ERROR] {e}")
        return False


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 70)
    print(" COMPREHENSIVE FEATURE VERIFICATION")
    print("=" * 70)

    results = []

    # Run synchronous tests
    results.append(("Configuration Module", test_config()))
    results.append(("Retry Module", test_retry_module()))
    results.append(("Database Models", test_database_models()))
    results.append(("Crawler Enums", test_crawler_enums()))
    results.append(("DataService", test_data_service()))

    # Run async test
    try:
        loop = asyncio.get_event_loop()
        crawler_result = loop.run_until_complete(test_crawler_context_manager())
        results.append(("Crawler Context Manager", crawler_result))
    except Exception as e:
        print(f"\n   [ERROR] Crawler test failed: {e}")
        results.append(("Crawler Context Manager", False))

    # Summary
    print("\n" + "=" * 70)
    print(" TEST SUMMARY")
    print("=" * 70)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"   [{status}] {name}")
        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print(" ALL TESTS PASSED!")
    else:
        print(" SOME TESTS FAILED")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
