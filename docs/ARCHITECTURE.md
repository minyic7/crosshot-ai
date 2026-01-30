# Crosshot AI - Architecture Documentation

## Overview

This is a multi-platform social media content scraping system with human simulation for stealth operation.

**Supported Platforms:**
- ✅ XHS (Xiaohongshu) - Fully implemented
- 🚧 X (Twitter) - Architecture ready, implementation pending

---

## Directory Structure

```
apps/
├── crawler/              # Platform-specific scrapers (技术层)
│   ├── base.py          # BaseCrawler interface
│   ├── xhs/             # XHS crawler (fully implemented)
│   │   └── scraper.py   # XhsCrawler
│   └── x/               # X/Twitter crawler (architecture ready)
│       └── scraper.py   # XCrawler (TODO)
│
├── jobs/                 # Business workflow layer (业务层)
│   ├── common/          # Shared job utilities
│   │   ├── base.py      # Config, Stats, helpers (platform-agnostic)
│   │   └── formatter.py # ShanghaiFormatter (timezone display)
│   ├── xhs/             # XHS jobs (fully implemented)
│   │   ├── human_simulation_job.py  # 24/7 production
│   │   └── scrape_content_job.py    # Testing tool
│   └── x/               # X/Twitter jobs (architecture ready)
│       ├── human_simulation_job.py  # 24/7 production (TODO)
│       └── scrape_content_job.py    # Testing tool (TODO)
│
├── services/            # Data persistence layer (服务层)
│   └── data_service.py  # Database operations, media downloads
│
├── database/            # Data models (数据层)
│   └── models.py        # SQLAlchemy models (Content, User, Comment, etc.)
│
└── config.py            # Pydantic settings (from .env)
```

---

## Layer Responsibilities

### 1. Crawler Layer (`apps/crawler/`)
**Purpose:** Platform-specific scraping logic (How to scrape)

- **BaseCrawler** - Abstract interface for all platforms
- **XhsCrawler** - XHS implementation (Playwright + stealth)
- **XCrawler** - X/Twitter implementation (TODO)

**Key Methods:**
- `scrape()` - Search for content
- `scrape_continuous()` - Continuous scroll-and-yield
- `scrape_user()` - Get user profile
- `scrape_comments()` - Get comments/replies

### 2. Jobs Layer (`apps/jobs/`)
**Purpose:** Complete business workflows (What to do)

#### Common Module (`jobs/common/`)
Platform-agnostic utilities shared by all jobs:

- **SimulationConfig** - Config for 24/7 production jobs
- **SimulationStats** - Statistics tracking
- **JobConfig** - Config for testing jobs
- **JobStats** - Testing job statistics
- **ShanghaiFormatter** - Timezone display (UTC+8)
- **Helper functions** - `human_delay()`, `log()`

#### Platform-Specific Jobs
Each platform has two job types:

**1. human_simulation_job.py** (24/7 Production)
- Work/Rest cycle (30-40 min work + 20-30 min rest)
- Ultra-conservative delays (7-60s)
- Continuous processing architecture
- Real-time 24h deduplication
- Complete workflow: search → content → author → comments → save

**2. scrape_content_job.py** (Testing Tool)
- Quick testing (1-3 contents)
- Shorter delays (2-5s)
- Validates all core functionality
- No work/rest cycles

### 3. Services Layer (`apps/services/`)
**Purpose:** Data persistence and processing

- Save content with media
- Save users
- Save comments
- Download media files (images, videos, avatars)
- Database session management

### 4. Database Layer (`apps/database/`)
**Purpose:** Data models

**Tables:**
- `contents` - Posts/tweets
- `users` - Authors and commenters
- `comments` - Comments/replies
- `content_history` - Version snapshots

---

## Design Patterns

### 1. Inheritance & Reuse

```
BaseCrawler (interface)
    ↓
├── XhsCrawler (implementation)
└── XCrawler (implementation)

jobs/common/base.py (shared config & stats)
    ↓
├── jobs/xhs/human_simulation_job.py (XHS-specific logic)
└── jobs/x/human_simulation_job.py (X-specific logic)
```

### 2. Context Manager Pattern

All crawlers use `async with` for proper resource management:

```python
async with XhsCrawler() as crawler:
    contents = await crawler.scrape("keyword")
    # Browser automatically closed after block
```

### 3. Generator Pattern (Continuous Processing)

```python
async for content in crawler.scrape_continuous(keyword):
    # Process each content immediately
    # Better time control, more natural behavior
```

### 4. Strategy Pattern

- Platform detection via `platform` field
- Different scrapers for different platforms
- Same business logic (jobs) for all platforms

---

## Configuration Management

### Environment Variables (`.env`)

```bash
# Crawler Settings (platform-agnostic)
CRAWLER_HEADLESS=false
CRAWLER_MAX_RETRIES=3

# XHS Settings
XHS_COOKIES_JSON=[...]

# X Settings (TODO)
X_COOKIES_JSON=[...]
```

### Pydantic Settings (`apps/config.py`)

- Type-safe configuration
- Automatic validation
- Easy testing with overrides

---

## Running Jobs

### XHS (Fully Functional)

```bash
# Local testing (1 content)
uv run python -m apps.jobs.xhs.scrape_content_job

# Local production (custom duration)
uv run python -m apps.jobs.xhs.human_simulation_job --duration 1440 --keywords "穿搭,海边"

# Docker (24/7)
docker-compose up human-simulation
```

### X/Twitter (Architecture Ready, Implementation TODO)

```bash
# Local testing
uv run python -m apps.jobs.x.scrape_content_job

# Local production
uv run python -m apps.jobs.x.human_simulation_job --duration 1440 --keywords "AI,tech"

# Docker (TODO: add to docker-compose.yml)
docker-compose up x-simulation
```

---

## Database Strategy

### Timezone Handling
- **Storage:** UTC (best practice, portable)
- **Display:** Asia/Shanghai (UTC+8, user-friendly)
- **Implementation:** ShanghaiFormatter for logs

### Deduplication
- **24h window:** Skip contents scraped within 24 hours
- **LRU cache:** In-memory dedup for current session (10k items)
- **Database query:** Real-time check before processing

---

## Stealth Features

### Browser Configuration
```python
# Anti-automation flags
'--disable-blink-features=AutomationControlled'

# JavaScript injection
Object.defineProperty(navigator, 'webdriver', { get: () => undefined })
```

### Human Simulation
- Randomized delays (7-60s)
- Work/Rest cycles (30-40 min work + 20-30 min rest)
- Natural scrolling patterns
- Randomized comment loading (8-15 clicks)

---

## Adding a New Platform

To add a new platform (e.g., Instagram, TikTok):

1. **Create crawler** (`apps/crawler/instagram/scraper.py`)
   - Inherit from `BaseCrawler`
   - Implement required methods

2. **Create jobs** (`apps/jobs/instagram/`)
   - Copy job templates from `jobs/x/`
   - Reuse `jobs/common` utilities
   - Implement platform-specific logic

3. **Update config** (`.env` and `apps/config.py`)
   - Add platform-specific settings

4. **Add docker service** (`docker-compose.yml`)
   ```yaml
   instagram-simulation:
     command: uv run python -m apps.jobs.instagram.human_simulation_job
   ```

---

## Testing Strategy

### Quick Testing
Use `scrape_content_job.py` for each platform:
- Tests all core functionality
- Fast feedback (2-5s delays)
- Single content validation

### Production Testing
Use `human_simulation_job.py` with short duration:
```bash
# Test for 30 minutes
uv run python -m apps.jobs.xhs.human_simulation_job --duration 30
```

---

## Future Enhancements

- [ ] Implement X/Twitter crawler
- [ ] Add Instagram support
- [ ] Add TikTok support
- [ ] Centralized monitoring dashboard
- [ ] Automatic cookie refresh
- [ ] Distributed scraping (multiple workers)
- [ ] Real-time data streaming
