FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace root (pyproject.toml + uv.lock)
COPY pyproject.toml uv.lock ./

# Copy all workspace member pyproject.toml files (needed for workspace resolution)
COPY apps/shared/pyproject.toml apps/shared/pyproject.toml
COPY apps/agent-crawler/pyproject.toml apps/agent-crawler/pyproject.toml
COPY apps/agent-coordinator/pyproject.toml apps/agent-coordinator/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml

# Copy source code for this agent and shared library
COPY apps/shared apps/shared
COPY apps/agent-crawler apps/agent-crawler

# Install only this package's dependencies
RUN uv sync --frozen --package agent-crawler

# Install Playwright browsers
RUN uv run --package agent-crawler playwright install --with-deps chromium

# Default command
CMD ["uv", "run", "--package", "agent-crawler", "python", "-m", "agent_crawler"]
