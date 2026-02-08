"""Stealth Playwright browser session for X.

Provides an async context manager that:
1. Launches Chromium with comprehensive anti-detection args
2. Injects stealth JS (17 detection surfaces patched)
3. Sends correct Sec-CH-UA client hints headers
4. Injects cookies from CookiesPool
5. Attaches GraphQL interceptor
6. Optionally configures residential proxy
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from shared.models.cookies import CookiesPool

from agent_crawler.stealth import UAProfile, build_stealth_js, random_profile

from .constants import (
    MAX_ACTION_DELAY,
    MIN_ACTION_DELAY,
    PAGE_LOAD_TIMEOUT_MS,
)
from .interceptor import GraphQLInterceptor

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Residential proxy configuration."""
    server: str
    username: str | None = None
    password: str | None = None


class XBrowserSession:
    """Async context manager for a stealth Playwright session on X.

    Usage:
        async with XBrowserSession(cookies=pool, proxy=proxy) as session:
            await session.goto("https://x.com/search?q=AI")
            data = await session.interceptor.wait_for("SearchTimeline")
    """

    def __init__(
        self,
        cookies: CookiesPool,
        proxy: ProxyConfig | None = None,
    ) -> None:
        self.cookies = cookies
        self.proxy = proxy

        # Set after __aenter__
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.interceptor = GraphQLInterceptor()

        self._pw: Playwright | None = None
        self._profile: UAProfile | None = None

    async def __aenter__(self) -> XBrowserSession:
        self._pw = await async_playwright().start()
        self._profile = random_profile()

        # ── Chromium launch args ──
        # Each flag addresses a specific detection vector.
        launch_args: dict[str, Any] = {
            "headless": True,
            "args": [
                # Core anti-detection
                "--disable-blink-features=AutomationControlled",

                # Performance / stability in Docker
                "--disable-dev-shm-usage",
                "--no-sandbox",

                # Reduce headless fingerprint surface
                "--disable-infobars",                          # No "controlled by automation" bar
                "--disable-background-timer-throttling",       # Prevent tab throttling
                "--disable-backgrounding-occluded-windows",    # Keep window active
                "--disable-renderer-backgrounding",            # Keep renderer active
                "--disable-ipc-flooding-protection",           # Prevent IPC throttle

                # Match viewport to launch size (consistency)
                "--window-size=1920,1080",

                # Disable features that leak headless
                "--disable-features=TranslateUI",              # No translate popup
                "--disable-default-apps",                      # No default app installs
                "--disable-hang-monitor",                      # No hang detection
                "--disable-prompt-on-repost",                  # No repost prompts
                "--disable-sync",                              # No sync features

                # GPU — use software rendering but hide it
                "--disable-gpu",
                "--disable-software-rasterizer",
            ],
        }

        # ── Residential proxy ──
        if self.proxy:
            proxy_dict: dict[str, str] = {"server": self.proxy.server}
            if self.proxy.username:
                proxy_dict["username"] = self.proxy.username
            if self.proxy.password:
                proxy_dict["password"] = self.proxy.password
            launch_args["proxy"] = proxy_dict

        self.browser = await self._pw.chromium.launch(**launch_args)

        # ── Browser context ──
        # Every field must be consistent with the UA profile.
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            screen={"width": 1920, "height": 1080},
            user_agent=self._profile.user_agent,
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
            has_touch=False,
            device_scale_factor=1,
            # Sec-CH-UA client hints — modern Chrome sends these on every request.
            # Missing or wrong values is a strong signal.
            extra_http_headers={
                "Sec-CH-UA": self._profile.sec_ch_ua,
                "Sec-CH-UA-Mobile": self._profile.sec_ch_ua_mobile,
                "Sec-CH-UA-Platform": self._profile.sec_ch_ua_platform,
            },
        )

        # ── Stealth JS ──
        stealth_js = build_stealth_js(self._profile)
        await self.context.add_init_script(stealth_js)

        # ── Cookies ──
        await self.context.add_cookies(self._format_cookies())

        # ── Page + interceptor ──
        self.page = await self.context.new_page()
        self.page.set_default_timeout(PAGE_LOAD_TIMEOUT_MS)
        self.page.on("response", self.interceptor.on_response)

        logger.info(
            "Browser session opened for %s (cookie=%s, ua=%s, platform=%s)",
            self.cookies.platform,
            self.cookies.name,
            self._profile.user_agent[:50] + "...",
            self._profile.platform,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()
        logger.info("Browser session closed")

    # ──────────────────────────────────────
    # Navigation helpers
    # ──────────────────────────────────────

    async def goto(self, url: str) -> None:
        """Navigate to URL and wait for network to settle."""
        assert self.page is not None
        await self.page.goto(url, wait_until="load")
        # Extra wait for JS-driven GraphQL calls to fire
        await self.random_delay(2.0, 4.0)

    async def scroll_down(self) -> None:
        """Scroll to bottom with human-like behavior."""
        assert self.page is not None
        # Smooth scroll in chunks instead of instant jump
        scroll_height = await self.page.evaluate("document.body.scrollHeight")
        current = await self.page.evaluate("window.scrollY")
        target = scroll_height
        step = random.randint(300, 600)

        while current < target:
            current = min(current + step, target)
            await self.page.evaluate(f"window.scrollTo(0, {current})")
            await asyncio.sleep(random.uniform(0.05, 0.15))

        await self.random_delay()

    async def random_delay(
        self,
        min_s: float = MIN_ACTION_DELAY,
        max_s: float = MAX_ACTION_DELAY,
    ) -> None:
        """Wait a random duration to simulate human behavior."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def screenshot_base64(self) -> str:
        """Take a screenshot and return as base64 string (for debugging)."""
        import base64
        assert self.page is not None
        buf = await self.page.screenshot(full_page=False)
        return base64.b64encode(buf).decode()

    async def get_page_title(self) -> str:
        """Get the current page title."""
        assert self.page is not None
        return await self.page.title()

    async def get_page_url(self) -> str:
        """Get the current page URL (useful to detect redirects)."""
        assert self.page is not None
        return self.page.url

    # ──────────────────────────────────────
    # Cookie formatting
    # ──────────────────────────────────────

    def _format_cookies(self) -> list[dict[str, Any]]:
        """Convert CookiesPool cookies to Playwright format."""
        pw_cookies = []
        for c in self.cookies.cookies:
            cookie: dict[str, Any] = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ".x.com"),
                "path": c.get("path", "/"),
            }
            if c.get("httpOnly") is not None:
                cookie["httpOnly"] = c["httpOnly"]
            if c.get("secure") is not None:
                cookie["secure"] = c["secure"]
            if c.get("sameSite"):
                ss = c["sameSite"].lower()
                # Chrome extension format → Playwright format
                if ss == "no_restriction":
                    cookie["sameSite"] = "None"
                elif ss in ("strict", "lax", "none"):
                    cookie["sameSite"] = ss.capitalize()
                    if cookie["sameSite"] == "None":
                        cookie["sameSite"] = "None"
                # "unspecified" → skip (use browser default)
            if c.get("expirationDate"):
                cookie["expires"] = c["expirationDate"]
            pw_cookies.append(cookie)
        return pw_cookies
