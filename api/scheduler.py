"""
api/scheduler.py
────────────────
Background APScheduler that runs every 30 seconds.
Drains the SQLite sync queue to PostgreSQL, and re-warms the SQLite read-cache
whenever:
  - PostgreSQL just came back online after being unreachable, OR
  - Items are still sitting in the queue while the server is online, OR
  - 10 minutes have elapsed since the last cache warm (keepalive refresh).

── CHANGELOG ────────────────────────────────────────────────────────────────
Bug 1 — CACHE WARM NEVER RE-TRIGGERED:
  The scheduler only called sync_pending_writes() but never warm_sqlite_cache().
  After a reconnect, pending writes were replayed but the read-cache remained
  stale (or empty on first start).

  Fix: call warm_sqlite_cache() on every offline→online transition AND every
  10 minutes while continuously online.

Bug 2 — STALE TCP PROBE IN SCHEDULER:
  is_postgres_online() caches its TCP result for 10 seconds.  The scheduler
  runs every 30 seconds, so it would read the cached value from the previous
  tick rather than doing a fresh probe, potentially missing a reconnect for
  up to 10 + 30 = 40 seconds.

  Fix: call _invalidate_pg_cache() at the top of each scheduler tick so the
  probe always reflects the current network state.
"""

import logging

logger = logging.getLogger(__name__)

_scheduler        = None
_was_online: bool | None = None
_last_warm_at: float     = 0.0   # monotonic timestamp of last warm_sqlite_cache()
_WARM_INTERVAL    = 600.0         # re-warm every 10 minutes while online


def _check_and_sync():
    """Job function — called every 30 s by the scheduler."""
    global _was_online, _last_warm_at

    import time
    from api.offline_manager import (
        is_postgres_online, sync_pending_writes,
        warm_sqlite_cache, _invalidate_pg_cache,
    )
    from api.models import OfflineSyncQueue

    # ── Always probe fresh — don't rely on the 10-second cache ──────────────
    _invalidate_pg_cache()
    online = is_postgres_online()

    if online:
        just_reconnected  = (_was_online is False)
        now               = time.monotonic()
        warm_overdue      = (now - _last_warm_at) >= _WARM_INTERVAL

        pending_count = (
            OfflineSyncQueue.objects
            .using('local')
            .filter(status=OfflineSyncQueue.STATUS_PENDING)
            .count()
        )

        if just_reconnected:
            logger.info('[SCHEDULER] PostgreSQL is BACK ONLINE — syncing + re-warming cache…')

        if pending_count > 0:
            logger.info(f'[SCHEDULER] {pending_count} pending item(s) found — syncing…')
            try:
                result = sync_pending_writes()
                logger.info(f'[SCHEDULER] Sync result: {result}')
            except Exception as exc:
                logger.error(f'[SCHEDULER] Sync failed: {exc}')

        # Warm the SQLite cache on reconnect or when the keepalive interval elapses
        if just_reconnected or warm_overdue:
            try:
                warm_sqlite_cache()
                _last_warm_at = time.monotonic()
            except Exception as exc:
                logger.error(f'[SCHEDULER] warm_sqlite_cache failed: {exc}')

    if _was_online is None:
        state = 'ONLINE' if online else 'OFFLINE'
        logger.info(f'[SCHEDULER] Initial DB state: {state}')

    _was_online = online


def start_scheduler():
    """Start the background scheduler. Safe to call multiple times — only starts once."""
    global _scheduler
    if _scheduler is not None:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.error(
            '[SCHEDULER] apscheduler not installed. '
            'Run: pip install apscheduler==3.10.4'
        )
        return

    _scheduler = BackgroundScheduler(timezone='Asia/Kolkata')
    _scheduler.add_job(
        _check_and_sync,
        trigger='interval',
        seconds=30,
        id='offline_sync_check',
        max_instances=1,
        replace_existing=True,
        misfire_grace_time=10,
    )
    _scheduler.start()
    logger.info('[SCHEDULER] Offline sync scheduler started — checks every 30 s')


def stop_scheduler():
    """Gracefully stop the scheduler (useful in tests)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None