"""X platform constants — user agents, stealth JS, timeouts."""

from __future__ import annotations

import random

# Recent Chrome user agents for rotation
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


def random_user_agent() -> str:
    """Pick a random Chrome user agent."""
    return random.choice(_USER_AGENTS)


# Stealth JavaScript — patches common automation fingerprints.
# Injected via context.add_init_script() before any page loads.
STEALTH_JS = """
// Overwrite navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Overwrite chrome.runtime (Playwright fingerprint)
if (!window.chrome) { window.chrome = {}; }
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        connect: function() {},
        sendMessage: function() {}
    };
}

// Remove Playwright-injected __playwright* globals
for (const key of Object.keys(window)) {
    if (key.startsWith('__playwright') || key.startsWith('__pw_')) {
        delete window[key];
    }
}

// Fix permissions query for notifications
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Fix plugins length
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// Fix languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});
"""

# Action delays (seconds) — randomized between actions for human-like behavior
MIN_ACTION_DELAY = 1.5
MAX_ACTION_DELAY = 4.0

# Page load timeout
PAGE_LOAD_TIMEOUT_MS = 30000

# GraphQL response wait timeout
GRAPHQL_WAIT_TIMEOUT = 15.0

# Scroll pagination settings
SCROLL_PAUSE_MIN = 2.0
SCROLL_PAUSE_MAX = 4.0
MAX_SCROLL_PAGES = 10
