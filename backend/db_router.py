"""
backend/db_router.py
─────────────────────
Automatic database router for the LIVE MENU PROJECT.

  • When PostgreSQL is reachable  →  all api app reads/writes go to 'default' (PostgreSQL)
  • When PostgreSQL is unreachable →  all api app reads/writes go to 'local'  (SQLite)

Django admin, auth, sessions, etc. always use 'default'.
The OfflineSyncQueue model always uses 'local' (it IS the offline store).
"""

from api.offline_manager import is_postgres_online


class OfflineRouter:

    # ── READ ─────────────────────────────────────────────────────────────────
    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'api':
            # OfflineSyncQueue lives only in SQLite
            if model.__name__ == 'OfflineSyncQueue':
                return 'local'
            return 'default' if is_postgres_online() else 'local'
        return 'default'

    # ── WRITE ────────────────────────────────────────────────────────────────
    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'api':
            if model.__name__ == 'OfflineSyncQueue':
                return 'local'
            return 'default' if is_postgres_online() else 'local'
        return 'default'

    # ── RELATIONS ────────────────────────────────────────────────────────────
    def allow_relation(self, obj1, obj2, **hints):
        # Allow all relations within the same database
        return True

    # ── MIGRATIONS ──────────────────────────────────────────────────────────
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # OfflineSyncQueue only migrates to SQLite
        if model_name == 'offlinesynccqueue':
            return db == 'local'
        # Everything else migrates to both (run with --database=local separately)
        return True