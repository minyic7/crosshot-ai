# Crawler Service

Web scraping service for multi-platform data collection.

## Structure

```
crawler/
├── __init__.py          # Package init
├── __main__.py          # Entry point
├── pyproject.toml       # Dependencies
├── Dockerfile           # Container image
└── README.md            # This file
```

## Development

```bash
# Install dependencies
cd apps/crawler
uv sync

# Run locally
uv run python -m crawler

# Run tests
uv run pytest
```

## Docker

```bash
# Build image
docker build -f apps/crawler/Dockerfile -t crawler:latest .

# Run container
docker run --rm crawler:latest
```

## Environment Variables

Add your environment variables to `.env` file.
