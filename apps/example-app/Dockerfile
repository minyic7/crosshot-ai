FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy application files
COPY apps/example-app /app

# Install Python dependencies
RUN uv sync --frozen

# Default command
CMD ["uv", "run", "python", "-m", "example_app"]
