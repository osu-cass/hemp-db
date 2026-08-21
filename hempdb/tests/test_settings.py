import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from hempdb.settings import database_configuration, database_ssl_options, env_value


class EnvironmentValueTests(SimpleTestCase):
    """Verify environment and Docker secret value loading."""

    def test_secret_file_takes_precedence(self):
        """Prefer a mounted secret over a direct environment value."""
        with TemporaryDirectory() as directory:
            secret_path = Path(directory) / 'secret'
            secret_path.write_text('file value\n')
            environment = {
                'HEMPDB_TEST_VALUE': 'environment value',
                'HEMPDB_TEST_VALUE_FILE': str(secret_path),
            }

            with patch.dict(os.environ, environment):
                value = env_value('HEMPDB_TEST_VALUE')

        self.assertEqual(value, 'file value')

    def test_environment_value_is_the_fallback(self):
        """Use a direct environment value when no secret file is set."""
        environment = {'HEMPDB_TEST_VALUE': 'environment value'}

        with patch.dict(os.environ, environment, clear=False):
            os.environ.pop('HEMPDB_TEST_VALUE_FILE', None)
            value = env_value('HEMPDB_TEST_VALUE')

        self.assertEqual(value, 'environment value')

    def test_database_parser_uses_resolved_secret_file_value(self):
        """Parse the mounted database URL when both sources are present."""
        with TemporaryDirectory() as directory:
            secret_path = Path(directory) / 'database_url'
            secret_path.write_text('mysql://user:pass@db/file_database\n')
            environment = {
                'DATABASE_URL': 'mysql://user:pass@db/environment_database',
                'DATABASE_URL_FILE': str(secret_path),
            }

            with patch.dict(os.environ, environment):
                database = database_configuration(
                    env_value('DATABASE_URL'),
                    conn_max_age=0,
                    use_ssl=False,
                )

        self.assertEqual(database['NAME'], 'file_database')

    def test_database_ssl_uses_explicit_ca(self):
        """Verify the database hostname against the configured CA."""
        self.assertEqual(
            database_ssl_options('/run/secrets/database_ca'),
            {
                'ca': '/run/secrets/database_ca',
                'check_hostname': True,
            },
        )
