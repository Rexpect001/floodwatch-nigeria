"""
Database connection utilities — asyncpg pool + Redis.

Usage in routers:
    from ..db import get_db, get_redis

Both are FastAPI dependency-injectable via Depends().
Pool is created once at startup (lifespan) and reused.
"""
import os
import asyncpg
import redis.asyncio as aioredis
from functools import lru_cache
from typing import AsyncGenerator

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://climate_user:password@localhost:5432/climate_ews")
REDIS_URL    = os.getenv("REDIS_URL",    "redis://localhost:6379")

# Module-level singletons (initialised on first call)
_db_pool: asyncpg.Pool | None   = None
_redis:   aioredis.Redis | None = None


async def init_db() -> asyncpg.Pool:
    """Create asyncpg connection pool. Called once at app startup."""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=2,
            max_size=20,
            command_timeout=30,
            # Register UUID codec so asyncpg returns UUID objects
            init=_register_codecs,
        )
    return _db_pool


async def _register_codecs(conn: asyncpg.Connection):
    await conn.set_type_codec(
        "uuid", encoder=str, decoder=str, schema="pg_catalog"
    )


async def close_db():
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


def init_redis() -> aioredis.Redis:
    """Create Redis client. Called once at app startup."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


# ── FastAPI Dependencies ──────────────────────────────────────

async def get_db() -> AsyncGenerator[asyncpg.Pool, None]:
    """Yield the shared asyncpg pool. Routers call .acquire() on it."""
    pool = await init_db()
    yield pool


async def get_redis() -> aioredis.Redis:
    """Yield the shared Redis client."""
    return init_redis()
