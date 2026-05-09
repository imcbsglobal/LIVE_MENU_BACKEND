from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        import api.signals  # keep your existing signals

        # Start the offline-sync background scheduler
        import os
        # Avoid double-start when Django's autoreloader spawns a second process
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('RUN_MAIN'):
            try:
                from api.scheduler import start_scheduler
                start_scheduler()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    f'[AppConfig] Could not start offline scheduler: {exc}'
                )