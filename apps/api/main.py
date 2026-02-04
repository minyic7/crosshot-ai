from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.agents import router as agents_router
from apps.api.stats import router as stats_router
from apps.config import get_settings
from apps.crawler.registry import get_crawler
from apps.database.models import Database
import apps.crawler.xhs  # Register xhs crawler

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stats_router, prefix="/api")
app.include_router(agents_router, prefix="/api")


@app.on_event("startup")
def on_startup():
    """Ensure all tables exist on startup."""
    settings = get_settings()
    db = Database(settings.database.path)
    db.init_db()


@app.get("/scrape/{platform}")
async def scrape(platform: str, keyword: str):
    crawler_class = get_crawler(platform)
    if not crawler_class:
        return {"error": "Platform not registered"}
    crawler = crawler_class()
    async with crawler:
        result = await crawler.scrape(keyword)
    return {"platform": platform, "keyword": keyword, "results": result}
