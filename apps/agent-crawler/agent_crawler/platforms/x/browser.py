"""Stealth Playwright browser session for X.

Provides an async context manager that:
1. Launches Chromium with anti-detection args
2. Injects stealth JS (patches navigator.webdriver, etc.)
3. Injects cookies from CookiesPool
4. Attaches GraphQL interceptor
5. Optionally configures residential proxy
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

from .constants import (
    MAX_ACTION_DELAY,
    MIN_ACTION_DELAY,
    PAGE_LOAD_TIMEOUT_MS,
    STEALTH_JS,
    random_user_agent,
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

    async def __aenter__(self) -> XBrowserSession:
        self._pw = await async_playwright().start()

        launch_args: dict[str, Any] = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-extensions",
            ],
        }

        # Residential proxy
        if self.proxy:
            proxy_dict: dict[str, str] = {"server": self.proxy.server}
            if self.proxy.username:
                proxy_dict["username"] = self.proxy.username
            if self.proxy.password:
                proxy_dict["password"] = self.proxy.password
            launch_args["proxy"] = proxy_dict

        self.browser = await self._pw.chromium.launch(**launch_args)

        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random_user_agent(),
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Stealth: inject anti-detection before any page loads
        await self.context.add_init_script(STEALTH_JS)

        # Inject cookies from pool
        await self.context.add_cookies(self._format_cookies())

        # Create page and attach interceptor
        self.page = await self.context.new_page()
        self.page.set_default_timeout(PAGE_LOAD_TIMEOUT_MS)
        self.page.on("response", self.interceptor.on_response)

        logger.info(
            "Browser session opened for %s (cookie=%s)",
            self.cookies.platform, self.cookies.name,
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
        """Navigate to URL with wait for network idle."""
        assert self.page is not None
        await self.page.goto(url, wait_until="domcontentloaded")
        # Small random delay after navigation
        await self.random_delay(0.5, 1.5)

    async def scroll_down(self) -> None:
        """Scroll to bottom to trigger lazy loading."""
        assert self.page is not None
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self.random_delay()

    async def random_delay(
        self,
        min_s: float = MIN_ACTION_DELAY,
        max_s: float = MAX_ACTION_DELAY,
    ) -> None:
        """Wait a random duration to simulate human behavior."""
        await asyncio.sleep(random.uniform(min_s, max_s))

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
                # Playwright expects: "Strict", "Lax", "None"
                ss = c["sameSite"]
                if ss.lower() in ("strict", "lax", "none"):
                    cookie["sameSite"] = ss.capitalize()
                    if cookie["sameSite"] == "None":
                        cookie["sameSite"] = "None"
            if c.get("expirationDate"):
                cookie["expires"] = c["expirationDate"]
            pw_cookies.append(cookie)
        return pw_cookies
