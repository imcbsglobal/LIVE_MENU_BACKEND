"""
api/scheduler.py
────────────────
Background APScheduler that runs every 30 seconds.
Drains the SQLite sync queue to PostgreSQL whenever:
  - PostgreSQL just came back online after being unreachable, OR
  - Items are still sitting in the queue while the server is online
    (covers records that landed in SQLite due to a brief router blip).
"""

import logging

logger     = logging.getLogger(__name__)
_scheduler = None
_was_online: bool | None = None   # tracks previous connectivity state


def _check_and_sync():
    """Job function — called every 30 s by the scheduler."""
    global _was_online
    from api.offline_manager import is_postgres_online, sync_pending_writes
    from api.models import OfflineSyncQueue

    online = is_postgres_online()

    if online:
        # ── CHANGED: sync on reconnect OR whenever pending items exist ──────
        # Original code only synced on the offline→online transition, so any
        # records stranded in SQLite while the server was already online
        # (e.g. from a brief TCP probe failure in the router) were never sent.
        just_reconnected = (_was_online is False)

        pending_count = (
            OfflineSyncQueue.objects
            .using('local')
            .filter(status=OfflineSyncQueue.STATUS_PENDING)
            .count()
        )

        if just_reconnected:
            logger.info('[SCHEDULER] PostgreSQL is BACK ONLINE — auto-syncing...')

        if pending_count > 0:
            logger.info(f'[SCHEDULER] {pending_count} pending item(s) found — syncing...')
            try:
                result = sync_pending_writes()
                logger.info(f'[SCHEDULER] Sync result: {result}')
            except Exception as exc:
                logger.error(f'[SCHEDULER] Sync failed: {exc}')
        # ── END CHANGED ──────────────────────────────────────────────────────

    if _was_online is None:
        # First run — log initial state
        state = 'ONLINE' if online else 'OFFLINE'
        logger.info(f'[SCHEDULER] Initial DB state: {state}')

    _was_online = online


def start_scheduler():
    """Start the background scheduler. Safe to call multiple times — only starts once."""
    global _scheduler
    if _scheduler is not None:
        return  # already running

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