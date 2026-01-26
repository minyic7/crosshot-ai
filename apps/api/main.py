from fastapi import FastAPI
from apps.crawler.registry import get_crawler
from apps.crawler.base import NoteItem
import apps.crawler.xhs  # Register xhs crawler

app = FastAPI()


@app.get("/scrape/{platform}")
async def scrape(platform: str, keyword: str):
    crawler_class = get_crawler(platform)
    if not crawler_class:
        return {"error": "Platform not registered"}
    crawler = crawler_class()
    async with crawler:
        result = await crawler.scrape(keyword)
    return {"platform": platform, "keyword": keyword, "results": result}