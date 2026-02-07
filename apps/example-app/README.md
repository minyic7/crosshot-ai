# Example App Template

Template for creating new microservices. Copy this folder to create a new app.

## Quick Start

1. Copy this folder:
   ```bash
   cp -r apps/example-app apps/my-new-app
   ```

2. Update `pyproject.toml`:
   - Change `name = "my-new-app"`
   - Add your dependencies

3. Update `Dockerfile`:
   - Change `COPY apps/example-app` to `COPY apps/my-new-app`

4. Add to workspace:
   ```toml
   # In root pyproject.toml
   [tool.uv.workspace]
   members = [
       "apps/crawler",
       "apps/my-new-app",  # Add this
   ]
   ```

5. Implement your logic in `__main__.py`

## Structure

```
example-app/
├── __init__.py          # Package init
├── __main__.py          # Entry point
├── pyproject.toml       # Dependencies
├── Dockerfile           # Container image
└── README.md            # This file
```

## Development

```bash
cd apps/my-new-app
uv sync
uv run python -m my_new_app
```

## Docker

```bash
docker build -f apps/my-new-app/Dockerfile -t my-new-app:latest .
docker run --rm my-new-app:latest
```
