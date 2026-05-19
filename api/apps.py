"""
api/apps.py
───────────
Django AppConfig for the 'api' application.

── CHANGELOG ────────────────────────────────────────────────────────────────
Bug — WARM CACHE NEVER TRIGGERED AT STARTUP:
  warm_sqlite_cache() was written but never called, so SQLite was always empty
  when PostgreSQL first went unreachable.  Django's AppConfig.ready() is the
  correct single entry-point for startup work that must run exactly once per
  server process.

  This file hooks into ready() to:
    1. Start the background scheduler (was already done in scheduler.py but
       only if something else called start_scheduler() — now guaranteed).
    2. Warm the SQLite cache in a daemon thread so it doesn't block the main
       process from accepting requests while the copy runs.

  To activate: add 'api.apps.ApiConfig' (or just 'api') to INSTALLED_APPS
  in settings.py.  If you already have 'api' listed without a default_auto_field
  or default_app_config, Django will pick this up automatically when the module
  is present.

IMPORTANT: ready() is called TWICE in DEBUG mode with runserver (one for the
  auto-reloader parent, once for the child).  The threading.Thread is a daemon,
  so it is harmless to start twice.  The _warming guard in warm_sqlite_cache()
  prevents overlapping runs.
"""

import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    name              = 'api'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # ── 1. Import signal handlers so they are registered ─────────────
        # (same pattern used by most Django projects)
        try:
            import api.signals  # noqa: F401
        except Exception as e:
            logger.warning(f'[ApiConfig] Could not import signals: {e}')

        # ── 2. Start the background APScheduler ──────────────────────────
        # Guard against running in management commands that don't need it
        # (e.g. `migrate`, `collectstatic`) where a scheduler is noise.
        import sys
        _skip_commands = {'migrate', 'makemigrations', 'collectstatic', 'shell',
                          'test', 'check', 'showmigrations', 'sqlmigrate'}
        running_command = sys.argv[1] if len(sys.argv) > 1 else ''

        if running_command not in _skip_commands:
            try:
                from api.scheduler import start_scheduler
                start_scheduler()
            except Exception as e:
                logger.warning(f'[ApiConfig] Could not start scheduler: {e}')

            # ── 3. Warm SQLite cache in the background ────────────────────
            # Run in a daemon thread so the HTTP server is not blocked.
            def _warm():
                try:
                    from api.offline_manager import warm_sqlite_cache
                    warm_sqlite_cache()
                except Exception as e:
                    logger.warning(f'[ApiConfig] warm_sqlite_cache failed: {e}')

            t = threading.Thread(target=_warm, daemon=True, name='sqlite-warm')
            t.start()
            logger.info('[ApiConfig] SQLite cache warm started in background thread.')