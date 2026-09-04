from django.apps import AppConfig
from importlib import import_module

class HelloworldConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "helloworld"
    verbose_name = "Hemp DB"

    # Runs on startup
    def ready(self):
        """Load signal handlers and cron registration at startup."""
        import_module("helloworld.signals")
        import_module("helloworld.cron")
