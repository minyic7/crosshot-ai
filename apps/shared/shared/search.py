"""OpenSearch client for full-text content search."""

import logging
from typing import Any

from opensearchpy import AsyncOpenSearch, helpers

logger = logging.getLogger(__name__)

_client: AsyncOpenSearch | None = None

INDEX_NAME = "contents"

INDEX_BODY: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "cjk_text": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "cjk_width", "cjk_bigram"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "topic_id": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "platform": {"type": "keyword"},
            "text": {"type": "text", "analyzer": "cjk_text"},
            "author_username": {"type": "keyword"},
            "author_display_name": {
                "type": "text",
                "analyzer": "cjk_text",
                "fields": {"raw": {"type": "keyword"}},
            },
            "hashtags": {"type": "keyword"},
            "lang": {"type": "keyword"},
            "processing_status": {"type": "keyword"},
            "crawled_at": {"type": "date"},
            "like_count": {"type": "integer"},
            "retweet_count": {"type": "integer"},
            "reply_count": {"type": "integer"},
            "views_count": {"type": "integer"},
        },
    },
}


def get_client() -> AsyncOpenSearch:
    """Get or create the async OpenSearch client (singleton)."""
    global _client
    if _client is None:
        from shared.config.settings import get_settings

        _client = AsyncOpenSearch(
            hosts=[get_settings().opensearch_url],
            use_ssl=False,
            verify_certs=False,
        )
    return _client


async def ensure_index() -> None:
    """Create the contents index if it doesn't exist (idempotent)."""
    client = get_client()
    if not await client.indices.exists(INDEX_NAME):
        await client.indices.create(INDEX_NAME, body=INDEX_BODY)
        logger.info("Created OpenSearch index '%s'", INDEX_NAME)
    else:
        logger.debug("OpenSearch index '%s' already exists", INDEX_NAME)


async def index_contents(docs: list[dict[str, Any]]) -> None:
    """Bulk index content documents to OpenSearch."""
    if not docs:
        return
    client = get_client()
    actions = []
    for doc in docs:
        doc_id = doc.pop("id", None) or doc.get("_id")
        actions.append({
            "_index": INDEX_NAME,
            "_id": doc_id,
            "_source": doc,
        })
    success, errors = await helpers.async_bulk(client, actions, raise_on_error=False)
    if errors:
        logger.warning("OpenSearch bulk index: %d succeeded, %d errors", success, len(errors))
    else:
        logger.debug("OpenSearch bulk index: %d documents indexed", success)


async def search_contents(
    query: str,
    *,
    platform: str | None = None,
    topic_id: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[str], int]:
    """Search OpenSearch, return (content_ids, total_count)."""
    client = get_client()

    must: list[dict[str, Any]] = [
        {
            "multi_match": {
                "query": query,
                "fields": ["text^3", "author_display_name", "author_username", "hashtags"],
                "type": "best_fields",
            },
        },
    ]
    filters: list[dict[str, Any]] = []
    if platform:
        filters.append({"term": {"platform": platform}})
    if topic_id:
        filters.append({"term": {"topic_id": topic_id}})
    if user_id:
        filters.append({"term": {"user_id": user_id}})

    body: dict[str, Any] = {
        "query": {"bool": {"must": must, "filter": filters}},
        "sort": [{"_score": "desc"}, {"crawled_at": "desc"}],
        "_source": False,
        "from": offset,
        "size": limit,
    }

    resp = await client.search(index=INDEX_NAME, body=body)
    ids = [hit["_id"] for hit in resp["hits"]["hits"]]
    total = resp["hits"]["total"]["value"]
    return ids, total


async def close_client() -> None:
    """Close the OpenSearch client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
