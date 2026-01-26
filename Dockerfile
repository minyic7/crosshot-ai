FROM python:3.13-slim

WORKDIR /app

# System dependencies for Playwright Chromium
RUN apt-get update && apt-get install -y \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Sync dependencies
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen

# Install Playwright browser
RUN uv run playwright install chromium

# Copy source
COPY . .

# Allow imports from apps/
ENV PYTHONPATH=/app

# Default: run API server
CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]