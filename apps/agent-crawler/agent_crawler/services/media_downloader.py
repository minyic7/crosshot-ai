"""Media downloader — stream-downloads media files to local storage.

Async, non-blocking. Failures are logged but never propagate to callers.
Supports images, videos, and animated GIFs with chunked streaming
to avoid memory issues with large video files.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# Limit concurrent downloads per batch
MAX_CONCURRENT_DOWNLOADS = 5

# Chunk size for streaming downloads (64 KB)
CHUNK_SIZE = 65536

# Download timeout per file (2 minutes for large videos)
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=120)

# Request headers to mimic a browser
DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


async def download_media_batch(
    media_items: list[dict[str, Any]],
    platform: str,
    content_id: str,
    crawled_date: str,
    base_path: str,
) -> list[dict[str, Any]]:
    """Download media items and return updated dicts with local_path.

    Each media item dict is expected to have:
    - "url": the image/thumbnail URL (media_url_https)
    - "video_url" (optional): the video/gif URL
    - "type": "photo", "video", or "animated_gif"

    After download, each item gets:
    - "local_path": path to the downloaded image file
    - "video_local_path" (if video): path to the downloaded video file
    - "download_status": "ok" | "failed"
    - "download_error" (if failed): error message
    """
    if not media_items:
        return media_items

    output_dir = Path(base_path) / platform / crawled_date / content_id
    output_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    async with aiohttp.ClientSession(
        timeout=DOWNLOAD_TIMEOUT,
        headers=DOWNLOAD_HEADERS,
    ) as session:
        tasks = [
            _download_single(session, item, output_dir, semaphore, idx)
            for idx, item in enumerate(media_items)
        ]
        results = await asyncio.gather(*tasks)

    return results


async def _download_single(
    session: aiohttp.ClientSession,
    item: dict[str, Any],
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    idx: int,
) -> dict[str, Any]:
    """Download a single media item (image + optional video)."""
    updated = dict(item)

    async with semaphore:
        try:
            # Download image/thumbnail
            image_url = item.get("url", "")
            if image_url:
                filename = _url_to_filename(image_url, f"img_{idx}")
                local_path = output_dir / filename
                if not local_path.exists():
                    await _download_file(session, image_url, local_path)
                updated["local_path"] = str(local_path)

            # Download video if present
            video_url = item.get("video_url", "")
            if video_url:
                vfilename = _url_to_filename(video_url, f"vid_{idx}")
                vlocal_path = output_dir / vfilename
                if not vlocal_path.exists():
                    await _download_file(session, video_url, vlocal_path)
                updated["video_local_path"] = str(vlocal_path)

            updated["download_status"] = "ok"
            logger.debug(
                "Downloaded media %d: %s%s",
                idx,
                image_url[:60] if image_url else "-",
                f" + video" if video_url else "",
            )

        except Exception as e:
            logger.warning(
                "Media download failed for item %d (%s): %s",
                idx, item.get("url", "?")[:60], e,
            )
            updated["download_status"] = "failed"
            updated["download_error"] = str(e)

    return updated


async def _download_file(
    session: aiohttp.ClientSession,
    url: str,
    dest: Path,
) -> None:
    """Stream-download a URL to a local file."""
    async with session.get(url) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                f.write(chunk)


def _url_to_filename(url: str, fallback: str) -> str:
    """Extract filename from URL, stripping query params."""
    parsed = urlparse(url)
    path = parsed.path
    name = path.rsplit("/", 1)[-1] if "/" in path else fallback

    # Remove query params embedded in name
    if "?" in name:
        name = name.split("?")[0]

    # Ensure we have a reasonable extension
    if "." not in name:
        name = f"{fallback}.bin"

    return name
