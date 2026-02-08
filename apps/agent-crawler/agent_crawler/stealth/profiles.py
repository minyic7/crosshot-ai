"""User-Agent profiles with consistent fingerprint fields.

Each profile bundles:
- User-Agent string
- navigator.platform (must match the UA's OS)
- Sec-CH-UA client hints headers (modern Chrome sends these on every request)

Mismatches between these fields are a strong bot detection signal.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class UAProfile:
    """A consistent user agent + platform fingerprint."""
    user_agent: str
    platform: str               # navigator.platform
    sec_ch_ua: str              # Sec-CH-UA header
    sec_ch_ua_platform: str     # Sec-CH-UA-Platform header
    sec_ch_ua_mobile: str       # Sec-CH-UA-Mobile header ("?0" = desktop)


# ──────────────────────────────────────────────
# Chrome 130-131 on Windows / macOS / Linux
# ──────────────────────────────────────────────

_PROFILES = [
    # Windows + Chrome 131
    UAProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        platform="Win32",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # macOS + Chrome 131
    UAProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        platform="MacIntel",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Windows + Chrome 130
    UAProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        platform="Win32",
        sec_ch_ua='"Google Chrome";v="130", "Chromium";v="130", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # macOS + Chrome 130
    UAProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        platform="MacIntel",
        sec_ch_ua='"Google Chrome";v="130", "Chromium";v="130", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Linux + Chrome 131
    UAProfile(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        platform="Linux x86_64",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Linux"',
        sec_ch_ua_mobile="?0",
    ),
]


def random_profile() -> UAProfile:
    """Pick a random UA profile with consistent fingerprint."""
    return random.choice(_PROFILES)
