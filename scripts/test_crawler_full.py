"""Full crawler functionality test - tests actual scraping with different sort options."""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.config import get_settings
from apps.crawler.xhs.scraper import XhsCrawler, SortBy, NoteType


async def test_crawler_functionality():
    """Test actual crawler functionality with real requests."""

    print("\n" + "=" * 70)
    print(" XHS CRAWLER FULL FUNCTIONALITY TEST")
    print("=" * 70)

    settings = get_settings()
    cookies = settings.xhs.get_cookies()

    if not cookies:
        print("\n[ERROR] No cookies configured in .env file")
        print("Please set XHS_COOKIES_JSON in your .env file")
        return False

    print(f"\nCookies loaded: {len(cookies)} cookies")

    keyword = "melbourne"
    results = {}

    async with XhsCrawler() as crawler:
        # Test 1: Default search (综合排序)
        print("\n" + "-" * 60)
        print("TEST 1: Default Search (综合排序) - Target 10 notes")
        print("-" * 60)

        try:
            notes_general = await crawler.scrape(
                keyword,
                sort_by=SortBy.GENERAL,
                max_notes=10,
            )
            results['general'] = notes_general
            print(f"Got {len(notes_general)} notes")
            if notes_general:
                print("Sample notes:")
                for i, note in enumerate(notes_general[:3]):
                    print(f"  {i+1}. {note.title[:30] if note.title else 'No title'}... | likes: {note.likes}")
            print("[PASS] General search works")
        except Exception as e:
            print(f"[FAIL] General search failed: {e}")
            import traceback
            traceback.print_exc()
            results['general'] = []

        await asyncio.sleep(3)

        # Test 2: Sort by newest (最新)
        print("\n" + "-" * 60)
        print("TEST 2: Sort by Newest (最新) - Target 10 notes")
        print("-" * 60)

        try:
            notes_newest = await crawler.scrape(
                keyword,
                sort_by=SortBy.NEWEST,
                max_notes=10,
            )
            results['newest'] = notes_newest
            print(f"Got {len(notes_newest)} notes")
            if notes_newest:
                print("Sample notes (should have low/recent likes):")
                for i, note in enumerate(notes_newest[:3]):
                    print(f"  {i+1}. {note.title[:30] if note.title else 'No title'}... | likes: {note.likes}")
            print("[PASS] Newest search works")
        except Exception as e:
            print(f"[FAIL] Newest search failed: {e}")
            import traceback
            traceback.print_exc()
            results['newest'] = []

        await asyncio.sleep(3)

        # Test 3: Sort by most liked (最多点赞)
        print("\n" + "-" * 60)
        print("TEST 3: Sort by Most Liked (最多点赞) - Target 10 notes")
        print("-" * 60)

        try:
            notes_popular = await crawler.scrape(
                keyword,
                sort_by=SortBy.MOST_LIKED,
                max_notes=10,
            )
            results['most_liked'] = notes_popular
            print(f"Got {len(notes_popular)} notes")
            if notes_popular:
                print("Sample notes (should have high likes):")
                for i, note in enumerate(notes_popular[:3]):
                    print(f"  {i+1}. {note.title[:30] if note.title else 'No title'}... | likes: {note.likes}")
            print("[PASS] Most liked search works")
        except Exception as e:
            print(f"[FAIL] Most liked search failed: {e}")
            import traceback
            traceback.print_exc()
            results['most_liked'] = []

        await asyncio.sleep(3)

        # Test 4: Filter by note type (图文)
        print("\n" + "-" * 60)
        print("TEST 4: Filter by Note Type (图文) - Target 10 notes")
        print("-" * 60)

        try:
            notes_image = await crawler.scrape(
                keyword,
                sort_by=SortBy.GENERAL,
                note_type=NoteType.IMAGE,
                max_notes=10,
            )
            results['image_only'] = notes_image
            print(f"Got {len(notes_image)} notes")
            if notes_image:
                print("Sample notes:")
                for i, note in enumerate(notes_image[:3]):
                    print(f"  {i+1}. {note.title[:30] if note.title else 'No title'}... | likes: {note.likes}")
            print("[PASS] Image filter works")
        except Exception as e:
            print(f"[FAIL] Image filter failed: {e}")
            import traceback
            traceback.print_exc()
            results['image_only'] = []

        await asyncio.sleep(3)

        # Test 5: Smart deduplication with 24h window
        print("\n" + "-" * 60)
        print("TEST 5: Smart Deduplication (24h window)")
        print("-" * 60)

        try:
            # Simulate URLs scraped at different times
            now = datetime.utcnow()

            # URLs from first search with timestamps
            recent_urls = {}
            for note in results.get('general', [])[:5]:
                if note.note_url:
                    # Mark as scraped 1 hour ago (within 24h window - should be SKIPPED)
                    recent_urls[note.note_url] = now - timedelta(hours=1)

            # Add some with older timestamps (outside 24h - should be INCLUDED for update)
            for note in results.get('general', [])[5:8]:
                if note.note_url:
                    # Mark as scraped 25 hours ago (outside window - should be re-scraped)
                    recent_urls[note.note_url] = now - timedelta(hours=25)

            print(f"Simulated recent URLs (within 24h, should skip): 5")
            print(f"Simulated old URLs (outside 24h, should re-scrape): 3")

            notes_dedup = await crawler.scrape(
                keyword,
                sort_by=SortBy.GENERAL,
                max_notes=15,
                recent_note_urls=recent_urls,
            )
            results['dedup'] = notes_dedup

            # Check if recent URLs were skipped
            recent_url_set = {url for url, ts in recent_urls.items() if ts > now - timedelta(hours=24)}
            found_recent = sum(1 for n in notes_dedup if n.note_url in recent_url_set)

            print(f"Got {len(notes_dedup)} notes after dedup")
            print(f"Recent URLs found in result (should be 0): {found_recent}")

            if found_recent == 0:
                print("[PASS] 24h dedup works - recent URLs were skipped")
            else:
                print(f"[WARN] Found {found_recent} recent URLs that should have been skipped")

        except Exception as e:
            print(f"[FAIL] Deduplication test failed: {e}")
            import traceback
            traceback.print_exc()
            results['dedup'] = []

        await asyncio.sleep(3)

        # Test 6: Smart scrolling - try to get more notes (tests continuous scroll)
        print("\n" + "-" * 60)
        print("TEST 6: Smart Scrolling - Target 30 notes")
        print("-" * 60)

        try:
            notes_scroll = await crawler.scrape(
                keyword,
                sort_by=SortBy.GENERAL,
                max_notes=30,  # Need to scroll to get 30
                max_scroll=50,
            )
            results['scroll'] = notes_scroll
            print(f"Got {len(notes_scroll)} notes (target was 30)")
            if len(notes_scroll) >= 25:  # Allow some margin
                print("[PASS] Smart scrolling works - got close to target")
            else:
                print(f"[WARN] Only got {len(notes_scroll)} notes, expected ~30")
        except Exception as e:
            print(f"[FAIL] Scroll test failed: {e}")
            import traceback
            traceback.print_exc()
            results['scroll'] = []

    # Summary
    print("\n" + "=" * 70)
    print(" TEST SUMMARY")
    print("=" * 70)

    all_passed = True
    for test_name, notes in results.items():
        status = "PASS" if len(notes) > 0 else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"  [{status}] {test_name}: {len(notes)} notes")

    # Verify sorting works by comparing likes
    print("\n" + "-" * 60)
    print("SORTING VERIFICATION")
    print("-" * 60)

    def parse_likes(likes_str):
        """Parse likes string to comparable number."""
        if not likes_str:
            return 0
        likes_str = str(likes_str)
        if '万' in likes_str:
            return float(likes_str.replace('万', '')) * 10000
        try:
            return int(likes_str)
        except:
            return 0

    if results.get('newest') and results.get('most_liked'):
        newest_likes = [parse_likes(n.likes) for n in results['newest'][:5]]
        popular_likes = [parse_likes(n.likes) for n in results['most_liked'][:5]]

        avg_newest = sum(newest_likes) / len(newest_likes) if newest_likes else 0
        avg_popular = sum(popular_likes) / len(popular_likes) if popular_likes else 0

        print(f"  Average likes (newest): {avg_newest:.0f}")
        print(f"  Average likes (most_liked): {avg_popular:.0f}")

        if avg_popular > avg_newest:
            print("  [PASS] Most liked has more likes than newest (sorting works!)")
        else:
            print("  [WARN] Sorting may not be working correctly")
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print(" ALL CRAWLER TESTS PASSED!")
    else:
        print(" SOME TESTS FAILED - PLEASE REVIEW")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_crawler_functionality())
    sys.exit(0 if success else 1)
