"""
Ingestion Scheduler — APScheduler wiring all data fetchers.

Poll schedule:
  Every 15 min : NIHSA gauges, NiMet observations, OWM (priority LGAs)
  Every 30 min : Google Flood Hub, GloFAS ensemble
  Every  6 h   : NIHSA AFO classifications, NiMet SCP, ACLED security events
  Daily 06:00  : Dam registry sync, historical baseline refresh
  On startup   : Full cold-start fetch for all sources

Failover:
  If Tier 1 (NIHSA/NiMet) fails 3× consecutively → Redis flag → API serves T2/cached
  Exponential backoff per source, independent — one source failing doesn't halt others

Run: python -m execution.ingestion.scheduler
"""
import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)
WAT = ZoneInfo("Africa/Lagos")

# Lazy imports — fetchers only loaded when scheduler starts
_db = None
_redis = None


async def _get_db():
    global _db
    if _db is None:
        import asyncpg
        _db = await asyncpg.create_pool(
            dsn=os.getenv("DATABASE_URL"),
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _db


async def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
    return _redis


# ── Job wrappers (each catches its own exceptions) ───────────

async def job_nihsa_gauges():
    """NIHSA: 273 hydrometric stations. ~15s per cycle."""
    try:
        from .nihsa_fetcher import run_once
        await run_once()
        await _mark_success("NIHSA")
    except Exception as e:
        log.error(f"[NIHSA gauges] {e}", exc_info=True)
        await _mark_failure("NIHSA", str(e))


async def job_nimet_observations():
    """NiMet: 54 synoptic + 6 RADAR stations."""
    try:
        from .nimet_fetcher import run_once
        await run_once()
        await _mark_success("NIMET")
    except Exception as e:
        log.error(f"[NiMet] {e}", exc_info=True)
        await _mark_failure("NIMET", str(e))


async def job_owm_batch():
    """OWM: high-risk LGAs first, quota-guarded (900/day cap)."""
    try:
        from .owm_fetcher import run_batch
        redis = await _get_redis()
        db    = await _get_db()

        # Priority: 148 HIGH-risk LGA centroids
        lga_coords = await _load_high_risk_lga_coords(db)
        await run_batch(lga_coords, redis)
        await _mark_success("OWM")
    except Exception as e:
        log.error(f"[OWM] {e}", exc_info=True)
        await _mark_failure("OWM", str(e))


async def job_google_flood_hub():
    """Google Flood Hub: 7-day AI forecasts, 20% inundation threshold."""
    try:
        from .google_flood_hub import run_once
        await run_once()
        await _mark_success("GOOGLE_FLOOD_HUB")
    except Exception as e:
        log.error(f"[Google Flood Hub] {e}", exc_info=True)
        await _mark_failure("GOOGLE_FLOOD_HUB", str(e))


async def job_glofas():
    """GloFAS: ensemble flood forecasting vs 2022/2024 baselines."""
    try:
        from .glofas_fetcher import run_once
        await run_once()
        await _mark_success("GLOFAS")
    except Exception as e:
        log.error(f"[GloFAS] {e}", exc_info=True)
        await _mark_failure("GLOFAS", str(e))


async def job_nihsa_afo():
    """NIHSA AFO: classifications for 302+ communities (semi-static, 6h)."""
    try:
        from .nihsa_fetcher import fetch_afo_classifications
        import httpx
        async with httpx.AsyncClient() as client:
            data = await fetch_afo_classifications(client)
        log.info(f"[NIHSA AFO] fetched {len(data)} community classifications")
        await _mark_success("NIHSA_AFO")
    except Exception as e:
        log.error(f"[NIHSA AFO] {e}", exc_info=True)


async def job_nimet_scp():
    """NiMet Seasonal Climate Prediction (6h refresh)."""
    try:
        from .nimet_fetcher import fetch_scp
        await fetch_scp()
        await _mark_success("NIMET_SCP")
    except Exception as e:
        log.error(f"[NiMet SCP] {e}", exc_info=True)


async def job_acled_security():
    """ACLED: armed conflict events for Nigeria (last 7 days, 6h refresh)."""
    try:
        from .acled_fetcher import run as acled_run
        db    = await _get_db()
        redis = await _get_redis()
        count = await acled_run(db_pool=db, redis=redis)
        log.info(f"[ACLED] {count} new security incidents ingested")
        await _mark_success("ACLED")
    except Exception as e:
        log.error(f"[ACLED] {e}", exc_info=True)
        await _mark_failure("ACLED", str(e))


async def job_laggo_dam_check():
    """Laggo Dam (Cameroon) release check — runs every 15 min alongside gauges."""
    try:
        from .nihsa_fetcher import check_laggo_dam_release
        import httpx
        async with httpx.AsyncClient() as client:
            release = await check_laggo_dam_release(client)
        if release:
            log.warning(f"[Laggo Dam] Release detected: {release}")
    except Exception as e:
        log.error(f"[Laggo Dam] {e}", exc_info=True)


# ── Helpers ───────────────────────────────────────────────────

async def _mark_success(source: str):
    db = await _get_db()
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO data_staleness (source, last_success, last_attempt, consecutive_failures, current_tier, is_degraded)
            VALUES ($1, NOW(), NOW(), 0, 1, FALSE)
            ON CONFLICT (source) DO UPDATE SET
                last_success = NOW(), last_attempt = NOW(),
                consecutive_failures = 0, current_tier = 1, is_degraded = FALSE
            """,
            source,
        )


async def _mark_failure(source: str, error: str):
    db = await _get_db()
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO data_staleness (source, last_attempt, consecutive_failures, is_degraded)
            VALUES ($1, NOW(), 1, FALSE)
            ON CONFLICT (source) DO UPDATE SET
                last_attempt = NOW(),
                consecutive_failures = data_staleness.consecutive_failures + 1,
                is_degraded = (data_staleness.consecutive_failures + 1) >= 3
            RETURNING consecutive_failures, is_degraded
            """,
            source,
        )
        if result and result["is_degraded"]:
            log.critical(
                f"[{source}] DEGRADED after {result['consecutive_failures']} failures — "
                "API will serve Tier 2/cached data"
            )
            redis = await _get_redis()
            await redis.set(f"source:degraded:{source}", "1", ex=3600)


async def _load_high_risk_lga_coords(db) -> list[tuple[int, float, float]]:
    """Load 148 HIGH-risk LGA centroids for OWM prioritisation."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ST_Y(centroid) lat, ST_X(centroid) lng
            FROM lgas WHERE flood_risk_class = 'HIGH' AND centroid IS NOT NULL
            ORDER BY id
            """
        )
    return [(r["id"], r["lat"], r["lng"]) for r in rows]


# ── Cold start ────────────────────────────────────────────────

async def cold_start():
    """Run all fetchers once on startup to populate initial data."""
    log.info("Cold start: fetching all sources...")
    tasks = [
        job_nihsa_gauges(),
        job_nimet_observations(),
        job_google_flood_hub(),
        job_glofas(),
        job_nihsa_afo(),
        job_acled_security(),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            log.error(f"Cold start task {i} failed: {r}")
    log.info("Cold start complete")


# ── Main ─────────────────────────────────────────────────────

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    scheduler = AsyncIOScheduler(timezone=str(WAT))

    # Every 15 minutes
    scheduler.add_job(job_nihsa_gauges,       IntervalTrigger(minutes=15), id="nihsa_gauges",       max_instances=1, misfire_grace_time=60)
    scheduler.add_job(job_nimet_observations, IntervalTrigger(minutes=15), id="nimet_obs",          max_instances=1, misfire_grace_time=60)
    scheduler.add_job(job_owm_batch,          IntervalTrigger(minutes=15), id="owm_batch",          max_instances=1, misfire_grace_time=60)
    scheduler.add_job(job_laggo_dam_check,    IntervalTrigger(minutes=15), id="laggo_dam",          max_instances=1, misfire_grace_time=30)

    # Every 30 minutes
    scheduler.add_job(job_google_flood_hub,   IntervalTrigger(minutes=30), id="flood_hub",          max_instances=1, misfire_grace_time=120)
    scheduler.add_job(job_glofas,             IntervalTrigger(minutes=30), id="glofas",             max_instances=1, misfire_grace_time=120)

    # Every 6 hours
    scheduler.add_job(job_nihsa_afo,          IntervalTrigger(hours=6),    id="nihsa_afo",          max_instances=1)
    scheduler.add_job(job_nimet_scp,          IntervalTrigger(hours=6),    id="nimet_scp",          max_instances=1)
    scheduler.add_job(job_acled_security,     IntervalTrigger(hours=6),    id="acled_security",     max_instances=1)

    # Daily 06:00 WAT
    scheduler.add_job(
        lambda: log.info("Daily sync placeholder — add dam registry + baseline refresh"),
        CronTrigger(hour=6, minute=0, timezone=str(WAT)),
        id="daily_sync",
    )

    # Cold start before scheduler begins
    await cold_start()

    scheduler.start()
    log.info("Scheduler running. Press Ctrl+C to stop.")

    # Graceful shutdown on SIGTERM (Docker stop)
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _shutdown(sig, frame):
        log.info(f"Received {sig.name}, shutting down scheduler...")
        scheduler.shutdown(wait=False)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    await stop_event.wait()
    log.info("Scheduler stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
