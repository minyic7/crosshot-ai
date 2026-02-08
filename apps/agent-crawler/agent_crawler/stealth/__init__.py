"""Stealth module — cross-platform anti-detection for Playwright browsers.

Usage:
    from agent_crawler.stealth import random_profile, build_stealth_js

    profile = random_profile()
    stealth_js = build_stealth_js(profile)
"""

from .injection import build_stealth_js
from .profiles import UAProfile, random_profile

__all__ = ["UAProfile", "random_profile", "build_stealth_js"]
