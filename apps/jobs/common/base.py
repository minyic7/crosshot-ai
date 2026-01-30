"""Common base classes and utilities for all job types.

This module provides platform-agnostic configuration, statistics tracking,
and helper functions that can be reused across different platforms (XHS, X, etc.).
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Human Simulation Job - Configuration & Statistics
# =============================================================================

@dataclass
class SimulationConfig:
    """Configuration for human simulation jobs (24/7 production).

    This config is platform-agnostic and can be used for any platform's
    human simulation job (XHS, X/Twitter, etc.).
    """
    # Duration
    duration_minutes: int = 10080  # 7 days default

    # Keywords (platform-specific search terms)
    keywords: List[str] = field(default_factory=list)  # Empty = browse homepage

    # Behavior probabilities
    prob_view_comments: float = 1.0  # Always view comments to get stats
    prob_view_author: float = 1.0  # Always view author profile
    prob_expand_sub_comments: float = 0.3  # 30% chance to expand sub-comments

    # Delays (seconds) - Ultra conservative for 24/7 operation
    delay_between_searches: Tuple[float, float] = (30, 60)  # 30-60s
    delay_reading_content: Tuple[float, float] = (10, 20)  # 10-20s reading content
    delay_reading_comments: Tuple[float, float] = (8, 15)  # 8-15s reading comments
    delay_before_action: Tuple[float, float] = (3, 6)  # 3-6s before action
    delay_scroll: Tuple[float, float] = (7, 18)  # 7-18s scroll delay
    delay_scroll_extra: Tuple[float, float] = (3, 8)  # Extra pause for natural browsing

    # Work/Rest cycle settings
    enable_hourly_breaks: bool = True  # Enable hourly work/rest cycle
    break_interval_minutes: int = 60  # Work duration per cycle (will be randomized 30-40)
    break_duration: Tuple[float, float] = (1200, 1800)  # 20-30 minutes rest

    # Limits per search session
    max_contents_per_search_min: int = 25  # Minimum contents per search
    max_contents_per_search_max: int = 60  # Maximum contents per search
    max_scroll_count: int = 30  # Maximum scroll attempts
    min_new_contents_per_scroll: int = 3  # Dynamic stop threshold

    # Comment loading (platform-specific but same range works for most)
    comment_load_clicks_min: int = 8  # Minimum clicks to load comments
    comment_load_clicks_max: int = 15  # Maximum clicks to load comments

    # Download settings
    download_images: bool = True
    download_videos: bool = True
    download_avatars: bool = True

    # Logging
    verbose: bool = True


@dataclass
class SimulationStats:
    """Statistics tracking for human simulation jobs.

    Platform-agnostic statistics that can be used across different platforms.
    """
    searches_completed: int = 0
    contents_viewed: int = 0
    contents_saved: int = 0
    users_saved: int = 0
    comments_saved: int = 0
    images_downloaded: int = 0
    videos_downloaded: int = 0
    breaks_taken: int = 0
    total_break_minutes: float = 0.0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# =============================================================================
# Content Scrape Job - Configuration & Statistics (Testing Tool)
# =============================================================================

@dataclass
class JobConfig:
    """Configuration for content scrape jobs (testing/development).

    Simpler config for one-off testing without work/rest cycles.
    Platform-agnostic.
    """
    # Search settings
    keyword: str = "test"  # Default test keyword
    max_contents: int = 1  # How many contents to fully scrape

    # Comment settings
    load_all_comments: bool = True  # Scroll to load all comments
    expand_sub_comments: bool = True  # Expand sub-comments

    # Download settings
    download_images: bool = True
    download_videos: bool = True
    download_avatars: bool = True

    # Human simulation delays (seconds) - shorter for testing
    min_delay: float = 2.0
    max_delay: float = 5.0

    # Logging
    verbose: bool = True


@dataclass
class JobStats:
    """Statistics for a content scrape job (testing/development).

    Platform-agnostic statistics for testing jobs.
    """
    contents_scraped: int = 0
    contents_saved: int = 0
    users_scraped: int = 0
    users_saved: int = 0
    comments_scraped: int = 0
    comments_saved: int = 0
    sub_comments_scraped: int = 0
    images_downloaded: int = 0
    videos_downloaded: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# =============================================================================
# Helper Functions
# =============================================================================

async def human_delay(
    delay_range: Tuple[float, float],
    action: str = "",
    verbose: bool = True
) -> None:
    """Add random delay to simulate human behavior.

    Args:
        delay_range: Tuple of (min_seconds, max_seconds)
        action: Description of the action (for logging)
        verbose: Whether to log the delay
    """
    delay = random.uniform(delay_range[0], delay_range[1])
    if verbose and action:
        logger.info(f"{action} (waiting {delay:.1f}s)")
    await asyncio.sleep(delay)


def log(message: str, level: str = "info") -> None:
    """Convenience logging function with level support.

    Args:
        message: Message to log
        level: Log level (info, warning, error, debug)
    """
    log_func = getattr(logger, level, logger.info)
    log_func(message)
