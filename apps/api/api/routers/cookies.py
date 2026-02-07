"""Cookies pool management endpoints.

CRUD for cookies stored in Redis. Each cookie set is stored as:
  cookies:pool:{id} → CookiesPool JSON (no expiry — persistent until deleted)
  cookies:index:{platform} → Set of cookie IDs for that platform
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_redis
from shared.models.cookies import CookiesPool

router = APIRouter(tags=["cookies"])


class CookiesCreate(BaseModel):
    """Request body for creating cookies."""

    platform: str
    name: str
    cookies: list[dict[str, Any]]


class CookiesUpdate(BaseModel):
    """Request body for updating cookies."""

    name: str | None = None
    cookies: list[dict[str, Any]] | None = None
    is_active: bool | None = None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

async def _get_cookie(cookie_id: str) -> CookiesPool:
    r = get_redis()
    data = await r.get(f"cookies:pool:{cookie_id}")
    if data is None:
        raise HTTPException(status_code=404, detail="Cookie not found")
    return CookiesPool.model_validate_json(data)


async def _save_cookie(cookie: CookiesPool) -> None:
    r = get_redis()
    await r.set(f"cookies:pool:{cookie.id}", cookie.model_dump_json())
    await r.sadd(f"cookies:index:{cookie.platform}", cookie.id)


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("/cookies")
async def list_cookies(platform: str | None = None) -> list[dict]:
    """List all cookies, optionally filtered by platform."""
    r = get_redis()
    results = []

    if platform:
        platforms = [platform]
    else:
        # Scan for all platform indexes
        platforms = []
        async for key in r.scan_iter("cookies:index:*"):
            platforms.append(key.removeprefix("cookies:index:"))

    for p in platforms:
        cookie_ids = await r.smembers(f"cookies:index:{p}")
        for cid in cookie_ids:
            data = await r.get(f"cookies:pool:{cid}")
            if data:
                cookie = CookiesPool.model_validate_json(data)
                results.append(cookie.model_dump(mode="json"))
            else:
                # Stale index entry — clean up
                await r.srem(f"cookies:index:{p}", cid)

    return results


@router.post("/cookies")
async def create_cookies(body: CookiesCreate) -> dict:
    """Add new cookies to the pool."""
    cookie = CookiesPool(
        platform=body.platform,
        name=body.name,
        cookies=body.cookies,
    )
    await _save_cookie(cookie)
    return cookie.model_dump(mode="json")


@router.get("/cookies/{cookie_id}")
async def get_cookies(cookie_id: str) -> dict:
    """Get a specific cookie by ID."""
    cookie = await _get_cookie(cookie_id)
    return cookie.model_dump(mode="json")


@router.patch("/cookies/{cookie_id}")
async def update_cookies(cookie_id: str, body: CookiesUpdate) -> dict:
    """Update cookies (name, cookies data, or active status)."""
    cookie = await _get_cookie(cookie_id)
    if body.name is not None:
        cookie.name = body.name
    if body.cookies is not None:
        cookie.cookies = body.cookies
    if body.is_active is not None:
        cookie.is_active = body.is_active
    await _save_cookie(cookie)
    return cookie.model_dump(mode="json")


@router.delete("/cookies/{cookie_id}")
async def delete_cookies(cookie_id: str) -> dict:
    """Delete cookies from the pool."""
    cookie = await _get_cookie(cookie_id)
    r = get_redis()
    await r.delete(f"cookies:pool:{cookie.id}")
    await r.srem(f"cookies:index:{cookie.platform}", cookie.id)
    return {"deleted": cookie.id}
