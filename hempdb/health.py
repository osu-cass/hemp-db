"""Health checks for container orchestration."""

import logging
from uuid import uuid4

from django.core.cache import cache
from django.db import connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET


logger = logging.getLogger(__name__)
CACHE_HEALTH_KEY = 'hempdb-health-ready'


def database_is_ready():
    """Return whether the default database accepts a query."""
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception as error:
        logger.warning('Database readiness check failed: %s', error)
        return False
    return True


def cache_is_ready():
    """Return whether the default cache supports a round trip."""
    cache_key = f'{CACHE_HEALTH_KEY}:{uuid4().hex}'
    try:
        cache.set(cache_key, 'ready', timeout=10)
        return cache.get(cache_key) == 'ready'
    except Exception as error:
        logger.warning('Cache readiness check failed: %s', error)
        return False
    finally:
        try:
            cache.delete(cache_key)
        except Exception as error:
            logger.warning('Cache readiness cleanup failed: %s', error)


@require_GET
def live(request):
    """Report that the Django process can serve requests."""
    return JsonResponse({'status': 'ok'})


@require_GET
def ready(request):
    """Report whether required backing services are available."""
    checks = {
        'database': database_is_ready(),
        'cache': cache_is_ready(),
    }
    is_ready = all(checks.values())
    return JsonResponse(
        {
            'status': 'ok' if is_ready else 'unavailable',
            'checks': checks,
        },
        status=200 if is_ready else 503,
    )
