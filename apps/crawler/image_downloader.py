"""Download and save images to local filesystem with retry support."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Self
from urllib.parse import urlparse

import aiohttp

from apps.config import get_settings
from apps.utils.retry import RetryConfig, retry_with_result

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of a download operation."""

    success: bool
    local_path: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0


class ImageDownloader:
    """Download and save images to local filesystem with retry support.

    Supports two usage patterns:

    1. Context manager (recommended for batch downloads):
        async with ImageDownloader() as downloader:
            await downloader.download_avatar(...)
            await downloader.download_note_images(...)
        # Session automatically closed

    2. Standalone calls (for single downloads):
        downloader = ImageDownloader()
        await downloader.download_avatar(...)  # Creates/closes session per call
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.xiaohongshu.com/",
    }

    def __init__(self, base_dir: str = "data/images"):
        self.settings = get_settings()
        self.base_dir = Path(base_dir)
        self.avatars_dir = self.base_dir / "avatars"
        self.covers_dir = self.base_dir / "covers"
        self.notes_dir = self.base_dir / "notes"
        self._session: Optional[aiohttp.ClientSession] = None

        # Create directories
        for d in [self.avatars_dir, self.covers_dir, self.notes_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self) -> Self:
        """Initialize shared aiohttp session."""
        self._session = aiohttp.ClientSession(headers=self.HEADERS)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Close shared aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    def _get_extension(self, url: str, content_type: str | None = None) -> str:
        """Get file extension from URL or content type."""
        # Try to get from URL
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            if ext in path:
                return ext if ext != ".jpeg" else ".jpg"

        # Try content type
        if content_type:
            if "jpeg" in content_type or "jpg" in content_type:
                return ".jpg"
            elif "png" in content_type:
                return ".png"
            elif "gif" in content_type:
                return ".gif"
            elif "webp" in content_type:
                return ".webp"

        return ".jpg"  # Default

    async def _do_download(
        self,
        url: str,
        save_path: Path,
        timeout: int = 30,
    ) -> Path:
        """Internal download method that can raise exceptions.

        Uses shared session if available, otherwise creates a temporary one.
        """
        # Use shared session or create temporary one
        if self._session:
            return await self._download_with_session(self._session, url, save_path, timeout)
        else:
            # Standalone usage: create temporary session
            async with aiohttp.ClientSession(headers=self.HEADERS) as session:
                return await self._download_with_session(session, url, save_path, timeout)

    async def _download_with_session(
        self,
        session: aiohttp.ClientSession,
        url: str,
        save_path: Path,
        timeout: int,
    ) -> Path:
        """Download using provided session."""
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status != 200:
                raise aiohttp.ClientError(f"HTTP {resp.status}")

            content = await resp.read()
            if not content:
                raise aiohttp.ClientError("Empty response body")

            # Get extension from content type
            ext = self._get_extension(url, resp.content_type)
            actual_path = save_path.with_suffix(ext)

            actual_path.write_bytes(content)
            return actual_path

    async def download_image(
        self,
        url: str,
        save_path: Path,
        timeout: int = 30,
    ) -> DownloadResult:
        """Download a single image with retry.

        Returns DownloadResult with success status, path, and error info.
        """
        if not url:
            return DownloadResult(success=False, error="Empty URL")

        # Skip if already exists
        if save_path.exists():
            return DownloadResult(success=True, local_path=str(save_path), attempts=0)

        # Check for existing file with different extension
        for ext in [".jpg", ".png", ".gif", ".webp"]:
            existing = save_path.with_suffix(ext)
            if existing.exists():
                return DownloadResult(
                    success=True, local_path=str(existing), attempts=0
                )

        # Configure retry
        retry_config = RetryConfig(
            max_retries=self.settings.crawler.max_retries,
            delay=self.settings.crawler.retry_delay,
            exceptions=(aiohttp.ClientError, asyncio.TimeoutError, OSError),
        )

        # Attempt download with retry
        result = await retry_with_result(
            self._do_download,
            url,
            save_path,
            timeout,
            config=retry_config,
        )

        if result.success:
            logger.debug(f"Downloaded {url} -> {result.value} ({result.attempts} attempts)")
            return DownloadResult(
                success=True,
                local_path=str(result.value),
                attempts=result.attempts,
            )
        else:
            error_msg = str(result.error) if result.error else "Unknown error"
            logger.warning(f"Failed to download {url}: {error_msg} ({result.attempts} attempts)")
            return DownloadResult(
                success=False,
                error=error_msg,
                attempts=result.attempts,
            )

    async def download_avatar(
        self, user_id: str, avatar_url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Download user avatar.

        Returns:
            Tuple of (local_path, error_message)
            - If success: (path, None)
            - If failure: (None, error_message)
        """
        if not avatar_url or not user_id:
            return None, "Missing user_id or avatar_url"

        # Use a placeholder extension, will be corrected by download_image
        save_path = self.avatars_dir / f"{user_id}.jpg"

        result = await self.download_image(avatar_url, save_path)

        if result.success and result.local_path:
            rel_path = str(Path(result.local_path).relative_to(self.base_dir.parent))
            return rel_path, None
        else:
            return None, result.error

    async def download_cover(
        self, note_id: str, cover_url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Download note cover image.

        Returns:
            Tuple of (local_path, error_message)
            - If success: (path, None)
            - If failure: (None, error_message)
        """
        if not cover_url or not note_id:
            return None, "Missing note_id or cover_url"

        save_path = self.covers_dir / f"{note_id}.jpg"

        result = await self.download_image(cover_url, save_path)

        if result.success and result.local_path:
            rel_path = str(Path(result.local_path).relative_to(self.base_dir.parent))
            return rel_path, None
        else:
            return None, result.error

    async def download_note_images(
        self,
        note_id: str,
        image_urls: list[str],
    ) -> tuple[list[str], list[str]]:
        """Download all images for a note.

        Returns:
            Tuple of (successful_paths, errors)
            - successful_paths: list of local paths for downloaded images
            - errors: list of error messages for failed downloads
        """
        if not image_urls or not note_id:
            return [], []

        tasks = []
        for i, url in enumerate(image_urls, 1):
            save_path = self.notes_dir / f"{note_id}_{i}.jpg"
            tasks.append(self.download_image(url, save_path))

        results = await asyncio.gather(*tasks)

        paths = []
        errors = []
        for i, result in enumerate(results):
            if result.success and result.local_path:
                rel_path = str(Path(result.local_path).relative_to(self.base_dir.parent))
                paths.append(rel_path)
            else:
                errors.append(f"Image {i+1}: {result.error}")

        return paths, errors

    async def download_all_for_user(
        self,
        user_id: str,
        avatar_url: str | None = None,
    ) -> dict:
        """Download all images for a user.

        Returns dict with local paths and errors.
        """
        result = {"avatar_path": None, "avatar_error": None}

        if avatar_url:
            path, error = await self.download_avatar(user_id, avatar_url)
            result["avatar_path"] = path
            result["avatar_error"] = error

        return result

    async def download_all_for_note(
        self,
        note_id: str,
        cover_url: str | None = None,
        image_urls: list[str] | None = None,
    ) -> dict:
        """Download all images for a note.

        Returns dict with local paths and errors.
        """
        result = {
            "cover_path": None,
            "cover_error": None,
            "image_paths": [],
            "image_errors": [],
        }

        # Download cover
        if cover_url:
            path, error = await self.download_cover(note_id, cover_url)
            result["cover_path"] = path
            result["cover_error"] = error

        # Download images
        if image_urls:
            paths, errors = await self.download_note_images(note_id, image_urls)
            result["image_paths"] = paths
            result["image_errors"] = errors

        return result
