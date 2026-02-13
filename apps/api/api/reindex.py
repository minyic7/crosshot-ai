"""One-time bulk reindex: PG contents → OpenSearch."""

import asyncio
import logging

from sqlalchemy import func, select

from shared.db.engine import get_session_factory
from shared.db.models import ContentRow
from shared.search import close_client, ensure_index, index_contents

logger = logging.getLogger(__name__)
BATCH_SIZE = 500


async def reindex_all() -> None:
    """Read all contents from PG and index them to OpenSearch."""
    await ensure_index()
    factory = get_session_factory()

    async with factory() as session:
        total = (await session.execute(select(func.count()).select_from(ContentRow))).scalar() or 0

    logger.info("Reindexing %d contents to OpenSearch", total)
    offset = 0
    indexed = 0

    while offset < total:
        async with factory() as session:
            rows = (
                await session.execute(
                    select(ContentRow).order_by(ContentRow.id).offset(offset).limit(BATCH_SIZE)
                )
            ).scalars().all()

        if not rows:
            break

        docs = []
        for row in rows:
            metrics = row.metrics or {}
            docs.append({
                "id": str(row.id),
                "topic_id": str(row.topic_id) if row.topic_id else None,
                "user_id": str(row.user_id) if row.user_id else None,
                "platform": row.platform,
                "text": row.text,
                "author_username": row.author_username,
                "author_display_name": row.author_display_name,
                "hashtags": row.hashtags or [],
                "lang": row.lang,
                "processing_status": row.processing_status,
                "crawled_at": row.crawled_at.isoformat() if row.crawled_at else None,
                "like_count": metrics.get("like_count", 0),
                "retweet_count": metrics.get("retweet_count", 0),
                "reply_count": metrics.get("reply_count", 0),
                "views_count": metrics.get("views_count", 0),
            })

        await index_contents(docs)
        indexed += len(docs)
        offset += BATCH_SIZE
        logger.info("Indexed %d/%d", indexed, total)

    await close_client()
    logger.info("Reindex complete: %d documents", indexed)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(reindex_all())
