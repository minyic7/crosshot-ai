"""X platform constants — timeouts and pagination settings."""

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
