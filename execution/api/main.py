"""
Nigeria Climate Early Warning System — FastAPI Gateway
Runs on port 8000; deployed behind nginx in Docker/K8s
"""
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .routers import forecasts, alerts, stations, reports, ussd, admin, voice_alerts
from .db import init_db, close_db, init_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect to DB + Redis with retries so health check
    # can respond even if backing services aren't ready immediately.
    import asyncio
    import logging
    logger = logging.getLogger("startup")

    for attempt in range(1, 6):
        try:
            await init_db()
            logger.info("Database pool ready")
            break
        except Exception as exc:
            logger.warning(f"DB connect attempt {attempt}/5 failed: {exc}")
            if attempt == 5:
                logger.error("DB unavailable at startup — continuing without pool")
            else:
                await asyncio.sleep(attempt * 2)

    for attempt in range(1, 4):
        try:
            redis = init_redis()
            await redis.ping()
            logger.info("Redis ready")
            break
        except Exception as exc:
            logger.warning(f"Redis connect attempt {attempt}/3 failed: {exc}")
            if attempt == 3:
                logger.error("Redis unavailable at startup — continuing without cache")
            else:
                await asyncio.sleep(attempt * 2)

    yield
    # Shutdown: close all connections cleanly
    await close_db()
    await close_redis()


app = FastAPI(
    title="Nigeria Climate Early Warning System API",
    version="1.0.0",
    description="Flood, heatwave, and climate alerts for 774 Nigerian LGAs",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=500)

_ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS",
    "https://floodwatch-ng.vercel.app,https://floodwatch-nigeria.vercel.app,http://localhost:3000"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://floodwatch.*\.vercel\.app",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(forecasts.router,    prefix="/api/v1/forecasts", tags=["Forecasts"])
app.include_router(alerts.router,       prefix="/api/v1/alerts",    tags=["Alerts"])
app.include_router(stations.router,     prefix="/api/v1/stations",  tags=["Stations"])
app.include_router(reports.router,      prefix="/api/v1/reports",   tags=["Community Reports"])
app.include_router(ussd.router,         prefix="/api/v1/ussd",      tags=["USSD"])
app.include_router(admin.router,        prefix="/api/v1/admin",     tags=["Admin"])
app.include_router(voice_alerts.router, prefix="/api/v1/voice",     tags=["Voice Pipeline"])


# Prometheus metrics endpoint
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "climate-ews"}


@app.get("/health/detailed")
async def health_detailed():
    """Deep health check — verifies DB + Redis connectivity."""
    from .db import _db_pool, _redis
    import time
    result: dict = {"service": "climate-ews", "checks": {}}
    overall = "ok"

    # DB check
    try:
        t0 = time.monotonic()
        async with _db_pool.acquire() as conn:  # type: ignore
            await conn.fetchval("SELECT 1")
        result["checks"]["database"] = {"status": "ok", "latency_ms": round((time.monotonic()-t0)*1000)}
    except Exception as e:
        result["checks"]["database"] = {"status": "error", "detail": str(e)}
        overall = "degraded"

    # Redis check
    try:
        t0 = time.monotonic()
        await _redis.ping()  # type: ignore
        result["checks"]["redis"] = {"status": "ok", "latency_ms": round((time.monotonic()-t0)*1000)}
    except Exception as e:
        result["checks"]["redis"] = {"status": "error", "detail": str(e)}
        overall = "degraded"

    result["status"] = overall
    return result
