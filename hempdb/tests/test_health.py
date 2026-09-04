from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


class HealthViewTests(SimpleTestCase):
    """Verify the container health endpoints."""

    def test_liveness_does_not_check_dependencies(self):
        """Liveness succeeds without accessing backing services."""
        with patch('hempdb.health.connections') as connections, patch(
            'hempdb.health.cache'
        ) as cache:
            response = self.client.get('/health/live/', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        connections.assert_not_called()
        cache.assert_not_called()

    @patch('hempdb.health.cache')
    @patch('hempdb.health.connections')
    def test_readiness_checks_database_and_cache(self, connections, cache):
        """Readiness succeeds after both dependency checks pass."""
        cache.get.return_value = 'ready'

        response = self.client.get('/health/ready/', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'status': 'ok',
                'checks': {'database': True, 'cache': True},
            },
        )
        connections['default'].cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
            'SELECT 1'
        )
        cache_key = cache.set.call_args.args[0]
        self.assertTrue(cache_key.startswith('hempdb-health-ready:'))
        cache.set.assert_called_once_with(cache_key, 'ready', timeout=10)
        cache.get.assert_called_once_with(cache_key)
        cache.delete.assert_called_once_with(cache_key)

    @patch('hempdb.health.cache')
    @patch('hempdb.health.connections')
    def test_readiness_fails_when_database_is_unavailable(self, connections, cache):
        """Readiness returns 503 when a required dependency fails."""
        connections['default'].cursor.side_effect = RuntimeError('unavailable')
        cache.get.return_value = 'ready'

        response = self.client.get('/health/ready/', secure=True)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                'status': 'unavailable',
                'checks': {'database': False, 'cache': True},
            },
        )

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_liveness_is_exempt_from_https_redirect(self):
        """Answer plain HTTP health probes instead of redirecting them."""
        with patch('hempdb.health.connections'), patch('hempdb.health.cache'):
            response = self.client.get('/health/live/')

        self.assertEqual(response.status_code, 200)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_other_paths_still_redirect_to_https(self):
        """Keep the HTTPS redirect for everything outside the health paths."""
        response = self.client.get('/')

        self.assertEqual(response.status_code, 301)
        self.assertTrue(response['Location'].startswith('https://'))
