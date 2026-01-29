"""Download and save images/videos to local filesystem with retry support."""

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


class MediaDownloader:
    """Download and save images/videos to local filesystem with retry support.

    Supports two usage patterns:

    1. Context manager (recommended for batch downloads):
        async with MediaDownloader() as downloader:
            await downloader.download_avatar(...)
            await downloader.download_content_media(...)
        # Session automatically closed

    2. Standalone calls (for single downloads):
        downloader = MediaDownloader()
        await downloader.download_avatar(...)  # Creates/closes session per call
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,video/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.xiaohongshu.com/",
    }

    IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"]
    VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".webm", ".m3u8"]

    def __init__(self, base_dir: str = "data"):
        self.settings = get_settings()
        self.base_dir = Path(base_dir)
        self.images_dir = self.base_dir / "images"
        self.videos_dir = self.base_dir / "videos"
        self.avatars_dir = self.images_dir / "avatars"
        self.covers_dir = self.images_dir / "covers"
        self.content_images_dir = self.images_dir / "contents"
        self.content_videos_dir = self.videos_dir / "contents"
        self._session: Optional[aiohttp.ClientSession] = None

        # Create directories
        for d in [self.avatars_dir, self.covers_dir, self.content_images_dir, self.content_videos_dir]:
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

    def _get_extension(self, url: str, content_type: str | None = None, media_type: str = "image") -> str:
        """Get file extension from URL or content type."""
        # Try to get from URL
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Check image extensions
        for ext in self.IMAGE_EXTENSIONS:
            if ext in path:
                return ext if ext != ".jpeg" else ".jpg"

        # Check video extensions
        for ext in self.VIDEO_EXTENSIONS:
            if ext in path:
                return ext

        # Try content type
        if content_type:
            content_type = content_type.lower()
            # Images
            if "jpeg" in content_type or "jpg" in content_type:
                return ".jpg"
            elif "png" in content_type:
                return ".png"
            elif "gif" in content_type:
                return ".gif"
            elif "webp" in content_type:
                return ".webp"
            elif "avif" in content_type:
                return ".avif"
            # Videos
            elif "mp4" in content_type:
                return ".mp4"
            elif "quicktime" in content_type or "mov" in content_type:
                return ".mov"
            elif "webm" in content_type:
                return ".webm"
            elif "avi" in content_type:
                return ".avi"

        # Default based on media type
        return ".jpg" if media_type == "image" else ".mp4"

    def _is_video_url(self, url: str) -> bool:
        """Check if URL is a video based on extension or patterns."""
        url_lower = url.lower()
        for ext in self.VIDEO_EXTENSIONS:
            if ext in url_lower:
                return True
        # XHS video URL patterns
        if "sns-video" in url_lower or "/video/" in url_lower:
            return True
        return False

    async def _do_download(
        self,
        url: str,
        save_path: Path,
        timeout: int = 30,
        media_type: str = "image",
    ) -> Path:
        """Internal download method that can raise exceptions.

        Uses shared session if available, otherwise creates a temporary one.
        """
        # Use shared session or create temporary one
        if self._session:
            return await self._download_with_session(self._session, url, save_path, timeout, media_type)
        else:
            # Standalone usage: create temporary session
            async with aiohttp.ClientSession(headers=self.HEADERS) as session:
                return await self._download_with_session(session, url, save_path, timeout, media_type)

    async def _download_with_session(
        self,
        session: aiohttp.ClientSession,
        url: str,
        save_path: Path,
        timeout: int,
        media_type: str = "image",
    ) -> Path:
        """Download using provided session."""
        # Videos may need longer timeout
        actual_timeout = timeout * 3 if media_type == "video" else timeout

        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=actual_timeout)
        ) as resp:
            if resp.status != 200:
                raise aiohttp.ClientError(f"HTTP {resp.status}")

            content = await resp.read()
            if not content:
                raise aiohttp.ClientError("Empty response body")

            # Get extension from content type
            ext = self._get_extension(url, resp.content_type, media_type)
            actual_path = save_path.with_suffix(ext)

            actual_path.write_bytes(content)
            return actual_path

    async def download_file(
        self,
        url: str,
        save_path: Path,
        timeout: int = 30,
        media_type: str = "image",
    ) -> DownloadResult:
        """Download a single file with retry.

        Returns DownloadResult with success status, path, and error info.
        """
        if not url:
            return DownloadResult(success=False, error="Empty URL")

        # Skip if already exists
        if save_path.exists():
            return DownloadResult(success=True, local_path=str(save_path), attempts=0)

        # Check for existing file with different extension
        extensions = self.VIDEO_EXTENSIONS if media_type == "video" else self.IMAGE_EXTENSIONS
        for ext in extensions:
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
            media_type,
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

        # Use a placeholder extension, will be corrected by download_file
        save_path = self.avatars_dir / f"{user_id}.jpg"

        result = await self.download_file(avatar_url, save_path, media_type="image")

        if result.success and result.local_path:
            rel_path = str(Path(result.local_path).relative_to(self.base_dir))
            return rel_path, None
        else:
            return None, result.error

    async def download_cover(
        self, content_id: str, cover_url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Download content cover image.

        Returns:
            Tuple of (local_path, error_message)
            - If success: (path, None)
            - If failure: (None, error_message)
        """
        if not cover_url or not content_id:
            return None, "Missing content_id or cover_url"

        save_path = self.covers_dir / f"{content_id}.jpg"

        result = await self.download_file(cover_url, save_path, media_type="image")

        if result.success and result.local_path:
            rel_path = str(Path(result.local_path).relative_to(self.base_dir))
            return rel_path, None
        else:
            return None, result.error

    async def download_content_images(
        self,
        content_id: str,
        image_urls: list[str],
    ) -> tuple[list[str], list[str]]:
        """Download all images for a content.

        Returns:
            Tuple of (successful_paths, errors)
            - successful_paths: list of local paths for downloaded images
            - errors: list of error messages for failed downloads
        """
        if not image_urls or not content_id:
            return [], []

        tasks = []
        for i, url in enumerate(image_urls, 1):
            save_path = self.content_images_dir / f"{content_id}_{i}.jpg"
            tasks.append(self.download_file(url, save_path, media_type="image"))

        results = await asyncio.gather(*tasks)

        paths = []
        errors = []
        for i, result in enumerate(results):
            if result.success and result.local_path:
                rel_path = str(Path(result.local_path).relative_to(self.base_dir))
                paths.append(rel_path)
            else:
                errors.append(f"Image {i+1}: {result.error}")

        return paths, errors

    async def download_content_videos(
        self,
        content_id: str,
        video_urls: list[str],
    ) -> tuple[list[str], list[str]]:
        """Download all videos for a content.

        Returns:
            Tuple of (successful_paths, errors)
            - successful_paths: list of local paths for downloaded videos
            - errors: list of error messages for failed downloads
        """
        if not video_urls or not content_id:
            return [], []

        tasks = []
        for i, url in enumerate(video_urls, 1):
            save_path = self.content_videos_dir / f"{content_id}_{i}.mp4"
            tasks.append(self.download_file(url, save_path, timeout=60, media_type="video"))

        results = await asyncio.gather(*tasks)

        paths = []
        errors = []
        for i, result in enumerate(results):
            if result.success and result.local_path:
                rel_path = str(Path(result.local_path).relative_to(self.base_dir))
                paths.append(rel_path)
            else:
                errors.append(f"Video {i+1}: {result.error}")

        return paths, errors

    async def download_all_for_user(
        self,
        user_id: str,
        avatar_url: str | None = None,
    ) -> dict:
        """Download all media for a user.

        Returns dict with local paths and errors.
        """
        result = {"avatar_path": None, "avatar_error": None}

        if avatar_url:
            path, error = await self.download_avatar(user_id, avatar_url)
            result["avatar_path"] = path
            result["avatar_error"] = error

        return result

    async def download_all_for_content(
        self,
        content_id: str,
        cover_url: str | None = None,
        image_urls: list[str] | None = None,
        video_urls: list[str] | None = None,
    ) -> dict:
        """Download all media for a content.

        Returns dict with local paths and errors.
        """
        result = {
            "cover_path": None,
            "cover_error": None,
            "image_paths": [],
            "image_errors": [],
            "video_paths": [],
            "video_errors": [],
        }

        # Download cover
        if cover_url:
            path, error = await self.download_cover(content_id, cover_url)
            result["cover_path"] = path
            result["cover_error"] = error

        # Download images
        if image_urls:
            paths, errors = await self.download_content_images(content_id, image_urls)
            result["image_paths"] = paths
            result["image_errors"] = errors

        # Download videos
        if video_urls:
            paths, errors = await self.download_content_videos(content_id, video_urls)
            result["video_paths"] = paths
            result["video_errors"] = errors

        return result


# Backward compatibility alias
ImageDownloader = MediaDownloader
