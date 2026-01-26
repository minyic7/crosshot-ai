import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apps.crawler.registry import get_crawler
import apps.crawler.xhs  # Register xhs crawler


async def run_scrape():
    crawler_class = get_crawler("xhs")
    if crawler_class:
        keywords = ["墨尔本爆款", "澳洲美妆"]
        for kw in keywords:
            crawler = crawler_class()
            async with crawler:
                result = await crawler.scrape(kw)
                print(f"[scheduler] keyword={kw}, results={len(result)}")


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_scrape, "interval", minutes=60)
    scheduler.start()
    print("[scheduler] Started, running every 60 minutes...")
    # Run once immediately for testing
    await run_scrape()
    # Keep alive
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
