"""
api/offline_manager.py
──────────────────────
Core offline/online controller for the LIVE MENU PROJECT.

Responsibilities:
  1. is_postgres_online()   — fast TCP probe with 10-second result cache
  2. get_active_db()        — returns 'default' (PostgreSQL) or 'local' (SQLite)
  3. queue_offline_write()  — saves a pending write to SQLite sync queue
  4. sync_pending_writes()  — replays all pending SQLite items to PostgreSQL via API
  5. warm_sqlite_cache()    — copies critical read tables PG → SQLite          ← NEW

── CHANGELOG ────────────────────────────────────────────────────────────────
Bug — SQLITE CACHE NEVER WARMED:
  The OfflineRouter switches reads to SQLite when PostgreSQL is unreachable,
  but nothing ever copied data INTO SQLite.  Offline mode therefore returned
  empty querysets for every model, making the app show blank menus, no tables,
  and broken customization/themes.

  Fix: warm_sqlite_cache() iterates over all critical models and bulk-copies
  their rows from PostgreSQL to SQLite using using('local').  It is called:
    • at server startup (via apps.py ready() hook)
    • by the scheduler on reconnect and every 10 minutes while continuously online
    • manually via the /api/trigger-sync/ endpoint

  It is safe to call concurrently — an internal threading.Lock prevents
  overlapping runs.  Each model is copied inside its own try/except so a
  failure on one table (e.g. a schema mismatch) doesn't abort the rest.

  Image / file fields are NOT transferred (binary blobs would explode SQLite).
  Only scalar fields and JSONField columns are copied.  The frontend already
  falls back to getImageSrc()'s default image when a URL is unreachable, so
  missing image blobs in SQLite are acceptable.
"""

import socket
import time
import logging
import threading
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)
_lock  = threading.Lock()

# ── Result cache for the TCP probe ──────────────────────────────────────────
_pg_cache: dict = {'online': None, 'checked_at': 0.0}
_PG_CACHE_TTL   = 10   # seconds

# ── Warm-cache guard — prevent overlapping warm runs ──────────────────────────
_warming = False


# ── 1. Connectivity probe ────────────────────────────────────────────────────

def is_postgres_online() -> bool:
    """
    TCP-level probe to check if PostgreSQL is reachable.
    Result is cached for _PG_CACHE_TTL seconds so the router does not
    open a new socket on every single database operation.
    """
    now = time.monotonic()
    with _lock:
        if (
            _pg_cache['online'] is not None
            and (now - _pg_cache['checked_at']) < _PG_CACHE_TTL
        ):
            return _pg_cache['online']

    try:
        db_cfg = settings.DATABASES['default']
        host   = db_cfg.get('HOST', 'localhost') or 'localhost'
        port   = int(db_cfg.get('PORT', 5432) or 5432)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        s.close()
        result = True
    except Exception:
        result = False

    with _lock:
        _pg_cache['online']     = result
        _pg_cache['checked_at'] = time.monotonic()

    return result


def _invalidate_pg_cache():
    """Force the next is_postgres_online() call to do a real probe."""
    with _lock:
        _pg_cache['online']     = None
        _pg_cache['checked_at'] = 0.0


# ── 2. Active DB alias ────────────────────────────────────────────────────────

def get_active_db() -> str:
    """Returns 'default' (PostgreSQL) when online, 'local' (SQLite) when offline."""
    return 'default' if is_postgres_online() else 'local'


# ── 3. Queue an offline write ─────────────────────────────────────────────────

def queue_offline_write(endpoint: str, method: str, payload: dict) -> None:
    """
    Persist a write operation to the local SQLite sync queue.
    Called automatically when PostgreSQL is unreachable.
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

    import requests as req

    pending = list(
        OfflineSyncQueue.objects.using('local')
        .filter(status=OfflineSyncQueue.STATUS_PENDING)
        .order_by('created_at')
    )

    if not pending:
        logger.info('[SYNC] No pending items.')
        return {'synced': 0, 'failed': 0, 'skipped': False}

    logger.info(f'[SYNC] Starting sync of {len(pending)} item(s)...')

    base     = 'http://127.0.0.1:8000'
    http_map = {
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
                    'X-Offline-Sync': 'true',
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


# ── 5. Warm the SQLite cache from PostgreSQL ─────────────────────────────────

# Models that must be available offline, with the fields to copy.
# File/image fields are intentionally excluded — binary blobs are not suitable
# for SQLite offline storage and the frontend degrades gracefully without them.
_WARM_TARGETS = [
    # (ModelPath, scalar_fields_to_copy, use_update_or_create_key)
    ('api.models.CompanyInfo',     None,  'client_id'),
    ('api.models.Category',        None,  'id'),
    ('api.models.Tax',             None,  'id'),
    ('api.models.MealType',        None,  'id'),
    ('api.models.Kitchen',         None,  'id'),
    ('api.models.Table',           None,  'id'),
    ('api.models.MenuItem',        None,  'id'),
    ('api.models.Customization',   None,  'id'),
    ('api.models.Banner',          None,  'id'),
    ('api.models.TVBanner',        None,  'id'),
]

# Fields that hold file/image references — skip them during the warm copy so
# we don't try to transfer binary content or get FileField path errors.
_FILE_FIELDS = frozenset({
    'image', 'logo', 'tv_logo', 'banner',
    'tv_theme2_left', 'tv_theme2_right',
    'tv_theme3_image', 'tv_theme3_video',
})


def warm_sqlite_cache() -> dict:
    """
    Copy all critical read-model rows from PostgreSQL → SQLite so offline
    mode serves real data instead of empty querysets.

    Safe to call from any thread.  Overlapping runs are skipped (not queued).

    Returns a summary dict: { model_name: {'copied': N, 'error': str|None} }
    """
    global _warming

    if not is_postgres_online():
        logger.info('[WARM] PostgreSQL offline — skipping cache warm.')
        return {}

    with _lock:
        if _warming:
            logger.info('[WARM] Already warming — skipping concurrent call.')
            return {}
        _warming = True

    results = {}
    try:
        import importlib

        for (model_path, _fields, pk_field) in _WARM_TARGETS:
            module_path, class_name = model_path.rsplit('.', 1)
            model_name = class_name
            try:
                module = importlib.import_module(module_path)
                Model  = getattr(module, class_name)

                # Identify concrete (non-file) fields we can copy
                concrete_fields = [
                    f.name for f in Model._meta.get_fields()
                    if hasattr(f, 'column')          # is a concrete DB column
                    and f.name not in _FILE_FIELDS   # not a file/image field
                ]

                rows_from_pg = list(
                    Model.objects.using('default').only(*concrete_fields)
                )
                copied = 0

                for row in rows_from_pg:
                    defaults = {
                        f: getattr(row, f)
                        for f in concrete_fields
                        if f != pk_field
                    }
                    try:
                        Model.objects.using('local').update_or_create(
                            **{pk_field: getattr(row, pk_field)},
                            defaults=defaults,
                        )
                        copied += 1
                    except Exception as row_err:
                        logger.warning(
                            f'[WARM] Skipping row {pk_field}='
                            f'{getattr(row, pk_field, "?")} for {model_name}: {row_err}'
                        )

                results[model_name] = {'copied': copied, 'error': None}
                logger.info(f'[WARM] {model_name}: copied {copied} row(s) to SQLite.')

            except Exception as model_err:
                results[model_name] = {'copied': 0, 'error': str(model_err)}
                logger.error(f'[WARM] {model_name}: failed — {model_err}')

    finally:
        with _lock:
            _warming = False

    logger.info(f'[WARM] Cache warm complete: {results}')
    return results