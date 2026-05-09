"""
api/offline_manager.py
──────────────────────
Core offline/online controller for the LIVE MENU PROJECT.

Responsibilities:
  1. is_postgres_online()   — fast TCP probe, no Django DB connection
  2. get_active_db()        — returns 'default' (PostgreSQL) or 'local' (SQLite)
  3. queue_offline_write()  — saves a pending write to SQLite sync queue
  4. sync_pending_writes()  — replays all pending SQLite items to PostgreSQL via API
"""

import socket
import logging
import threading
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)
_lock  = threading.Lock()


# ── 1. Connectivity probe ────────────────────────────────────────────────────

def is_postgres_online() -> bool:
    """
    TCP-level probe to check if PostgreSQL is reachable.
    Does NOT open a Django DB connection (fast, < 3 s timeout).
    """
    try:
        db_cfg = settings.DATABASES['default']
        host   = db_cfg.get('HOST', 'localhost') or 'localhost'
        port   = int(db_cfg.get('PORT', 5432) or 5432)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


# ── 2. Active DB alias ────────────────────────────────────────────────────────

def get_active_db() -> str:
    """Returns 'default' (PostgreSQL) when online, 'local' (SQLite) when offline."""
    return 'default' if is_postgres_online() else 'local'


# ── 3. Queue an offline write ─────────────────────────────────────────────────

def queue_offline_write(endpoint: str, method: str, payload: dict) -> None:
    """
    Persist a write operation to the local SQLite sync queue.
    Called automatically when PostgreSQL is unreachable.

    Args:
        endpoint : API path  e.g.  '/api/orders/'
        method   : HTTP verb e.g.  'POST'
        payload  : dict of the request body
    """
    from api.models import OfflineSyncQueue
    with _lock:
        OfflineSyncQueue.objects.using('local').create(
            endpoint=endpoint,
            method=method.upper(),
            payload=payload,
            status=OfflineSyncQueue.STATUS_PENDING,
        )
    logger.info(f'[OFFLINE] Queued {method.upper()} {endpoint}')


# ── 4. Sync all pending items to PostgreSQL ───────────────────────────────────

def sync_pending_writes() -> dict:
    """
    Replay every pending item in the SQLite queue against the live PostgreSQL
    API (via HTTP to localhost:8000).  Should only be called when online.

    Returns a dict with synced / failed counts.
    """
    from api.models import OfflineSyncQueue

    if not is_postgres_online():
        logger.info('[SYNC] PostgreSQL still offline — skipping sync.')
        return {'synced': 0, 'failed': 0, 'skipped': True}

    import requests as req  # stdlib-free alias — 'requests' is in your requirements.txt

    pending = list(
        OfflineSyncQueue.objects.using('local')
        .filter(status=OfflineSyncQueue.STATUS_PENDING)
        .order_by('created_at')
    )

    if not pending:
        logger.info('[SYNC] No pending items.')
        return {'synced': 0, 'failed': 0, 'skipped': False}

    logger.info(f'[SYNC] Starting sync of {len(pending)} item(s)...')

    base      = 'http://127.0.0.1:8000'
    http_map  = {
        'POST':   req.post,
        'PUT':    req.put,
        'PATCH':  req.patch,
        'DELETE': req.delete,
    }
    synced_count = 0
    failed_count = 0

    for item in pending:
        try:
            fn       = http_map.get(item.method, req.post)
            response = fn(
                f'{base}{item.endpoint}',
                json=item.payload,
                headers={
                    'Content-Type':   'application/json',
                    'X-Offline-Sync': 'true',   # header so views can detect replays
                },
                timeout=10,
            )
            if response.status_code < 400:
                item.status    = OfflineSyncQueue.STATUS_SYNCED
                item.synced_at = datetime.now(timezone.utc)
                synced_count  += 1
                logger.info(f'[SYNC] ✓ {item.method} {item.endpoint}')
            else:
                item.status    = OfflineSyncQueue.STATUS_FAILED
                item.error_msg = response.text[:500]
                item.retries  += 1
                failed_count  += 1
                logger.warning(f'[SYNC] ✗ {item.method} {item.endpoint} → HTTP {response.status_code}')
        except Exception as exc:
            item.status    = OfflineSyncQueue.STATUS_FAILED
            item.error_msg = str(exc)[:500]
            item.retries  += 1
            failed_count  += 1
            logger.error(f'[SYNC] ✗ {item.method} {item.endpoint} → {exc}')
        finally:
            item.save(using='local')

    logger.info(f'[SYNC] Complete — synced={synced_count} failed={failed_count}')
    return {'synced': synced_count, 'failed': failed_count, 'skipped': False}