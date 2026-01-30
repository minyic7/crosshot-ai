"""Test script to scrape X (Twitter) following timeline.

This is a quick test to validate:
1. Cookie authentication works
2. Can access following timeline
3. Can extract post data
4. Summarize what's happening

Usage:
    uv run python scripts/test_x_scraper.py
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright


# X.com cookies (from user's browser)
X_COOKIES = [
    {
        "name": "__cf_bm",
        "value": "OBZ26MirNM6vd8yhtVAp7.1ZzzdIOOcJGWRp0atG7MQ-1769733453.2505116-1.0.1.1-OKX.R33NyesC4muXLMbOG_6or21ECJBBOf8d8yVoWyBMYbsisEsiHHbUUidv0MWOIIUbCU9zCrSb9dQYV3.tdaDhBuw_NDFhaK6K6ltXfQ04Wtx8Xmy7lRC7Hk3Lwh_J",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "__cuid",
        "value": "2dc9aad0cce8474bb84c2801eca588b2",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "att",
        "value": "1-s9PCe0x5g4APJvjNNDE1zesVdVAdhlJ2NX85Q34u",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "auth_token",
        "value": "c0bee2065a1c40659c598205684d6076279cae5d",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "ct0",
        "value": "e0576a8f439f96fb9c33157dd1226fbc3c34ded76fb4897ed92cd8e557fb1087017990aa1f8afe072c8d656f0f04652ae7632d5ca4451df4e24e879729ad7173e4b1c7bb954d65ae49102d0ea0fd7949",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "external_referer",
        "value": "padhuUp37zjgzgv1mFWxJ12Ozwit7owX|0|8e8t2xd8A2w%3D",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "gt",
        "value": "2017034243394916466",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "guest_id",
        "value": "v1%3A176973341294542998",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "guest_id_ads",
        "value": "v1%3A176973341294542998",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "guest_id_marketing",
        "value": "v1%3A176973341294542998",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "kdt",
        "value": "BiSwOVntMG7tp0jJ6rCZFYHOyklK0wFjNMqQfSUl",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "personalization_id",
        "value": "\"v1_SBDJ84K4vMH9SsXMXf2f1g==\"",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "twid",
        "value": "u%3D1509796438242332676",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "g_state",
        "value": "{\"i_l\":0,\"i_ll\":1769733445611}",
        "domain": "x.com",
        "path": "/"
    },
    {
        "name": "lang",
        "value": "en",
        "domain": "x.com",
        "path": "/"
    }
]


async def scrape_following_timeline():
    """Scrape posts from X following timeline and summarize."""

    print("=" * 70)
    print("X (Twitter) Following Timeline Scraper - Test Script")
    print("=" * 70)

    async with async_playwright() as p:
        # Launch browser (visible for debugging)
        print("\n[1/6] Launching browser...")
        browser = await p.chromium.launch(
            headless=False,  # Show browser for debugging
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )

        # Create context with stealth settings
        print("[2/6] Creating browser context with stealth settings...")
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        # Inject anti-detection JS
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        # Add cookies
        print("[3/6] Loading cookies...")
        await context.add_cookies(X_COOKIES)

        # Navigate to following timeline
        print("[4/6] Navigating to X following timeline...")
        page = await context.new_page()

        # Try /home first (default timeline shows following)
        await page.goto('https://x.com/home', wait_until='domcontentloaded')
        await asyncio.sleep(5)  # Wait for dynamic content

        # Take screenshot for debugging
        screenshot_path = "data/debug_screenshots/x_following_timeline.png"
        import os
        os.makedirs("data/debug_screenshots", exist_ok=True)
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"   Screenshot saved: {screenshot_path}")

        # Check if we're logged in
        current_url = page.url
        print(f"   Current URL: {current_url}")

        if "login" in current_url or "i/flow" in current_url:
            print("\n❌ Not logged in! Cookies may have expired.")
            print("   Please check the screenshot and update cookies if needed.")
            await browser.close()
            return

        print("\n✅ Successfully logged in!")

        # Extract posts from timeline
        print("\n[5/6] Extracting posts from timeline...")

        # Wait for tweets to load
        await page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)

        # Scroll to load more posts
        print("   Scrolling to load more posts...")
        for i in range(3):  # Scroll 3 times
            await page.evaluate('window.scrollBy(0, window.innerHeight)')
            await asyncio.sleep(2)

        # Extract post data using JavaScript
        posts_data = await page.evaluate("""
            () => {
                const articles = document.querySelectorAll('article[data-testid="tweet"]');
                const posts = [];

                articles.forEach(article => {
                    try {
                        // Author info
                        const authorElement = article.querySelector('[data-testid="User-Name"]');
                        const author = authorElement ? authorElement.innerText.split('\\n')[0] : 'Unknown';
                        const username = authorElement ? authorElement.innerText.split('\\n')[1] : '';

                        // Post text
                        const tweetTextElement = article.querySelector('[data-testid="tweetText"]');
                        const text = tweetTextElement ? tweetTextElement.innerText : '';

                        // Time
                        const timeElement = article.querySelector('time');
                        const timestamp = timeElement ? timeElement.getAttribute('datetime') : '';
                        const timeAgo = timeElement ? timeElement.innerText : '';

                        // Engagement metrics
                        const replyButton = article.querySelector('[data-testid="reply"]');
                        const retweetButton = article.querySelector('[data-testid="retweet"]');
                        const likeButton = article.querySelector('[data-testid="like"]');

                        const replies = replyButton ? replyButton.getAttribute('aria-label') || '0' : '0';
                        const retweets = retweetButton ? retweetButton.getAttribute('aria-label') || '0' : '0';
                        const likes = likeButton ? likeButton.getAttribute('aria-label') || '0' : '0';

                        // URL
                        const linkElement = article.querySelector('a[href*="/status/"]');
                        const url = linkElement ? 'https://x.com' + linkElement.getAttribute('href') : '';

                        posts.push({
                            author,
                            username,
                            text,
                            timestamp,
                            timeAgo,
                            replies,
                            retweets,
                            likes,
                            url
                        });
                    } catch (e) {
                        console.error('Error extracting post:', e);
                    }
                });

                return posts;
            }
        """)

        print(f"\n✅ Extracted {len(posts_data)} posts from timeline")

        # Save raw data
        output_file = "data/x_following_posts.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(posts_data, f, indent=2, ensure_ascii=False)
        print(f"   Raw data saved: {output_file}")

        # Analyze and summarize
        print("\n[6/6] Analyzing timeline...")
        print("=" * 70)
        print("SUMMARY: What's happening in your following")
        print("=" * 70)

        if not posts_data:
            print("\nNo posts found. Timeline might be empty or posts didn't load.")
        else:
            # Group by author
            authors = {}
            for post in posts_data:
                author = post['author']
                if author not in authors:
                    authors[author] = []
                authors[author].append(post)

            print(f"\n📊 Stats:")
            print(f"   Total posts: {len(posts_data)}")
            print(f"   Unique authors: {len(authors)}")

            print(f"\n👥 Most active authors:")
            sorted_authors = sorted(authors.items(), key=lambda x: len(x[1]), reverse=True)
            for author, author_posts in sorted_authors[:5]:
                print(f"   • {author}: {len(author_posts)} posts")

            print(f"\n📝 Recent posts preview:")
            for i, post in enumerate(posts_data[:10], 1):
                print(f"\n   [{i}] {post['author']} ({post['username']})")
                print(f"       Time: {post['timeAgo']}")
                print(f"       Text: {post['text'][:100]}{'...' if len(post['text']) > 100 else ''}")
                print(f"       💬 {post['replies']} | 🔁 {post['retweets']} | ❤️ {post['likes']}")
                if post['url']:
                    print(f"       URL: {post['url']}")

        print("\n" + "=" * 70)
        print("Test completed! Browser will stay open for 10 seconds for inspection.")
        print("=" * 70)

        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(scrape_following_timeline())
