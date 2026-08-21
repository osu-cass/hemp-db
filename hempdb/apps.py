"""Application configuration overrides for third-party integrations."""

from django.apps import AppConfig


class DjangoCronConfig(AppConfig):
    """Match django-cron's primary keys to its shipped migrations."""

    default_auto_field = 'django.db.models.AutoField'
    name = 'django_cron'
