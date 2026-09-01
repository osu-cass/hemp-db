"""Tests for local permission-account seeding."""

import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

@override_settings(DEBUG=True)
class SeedUsersTests(TestCase):
    """Verify the five local accounts and their permission boundaries."""

    def _seed(self):
        """Run users-only seeding with a known test password."""
        with patch.dict(os.environ, {"DEV_SEED_PASSWORD": "shared-test-password"}):
            call_command("seed_test_users", stdout=StringIO())

    def test_command_creates_the_access_matrix_without_csv_files(self):
        """Create every ticket role without requiring demonstration CSVs."""
        self._seed()
        users = {
            username: get_user_model().objects.get(username=username)
            for username in (
                "test_superuser", "test_staff", "test_editor",
                "test_reviewer", "test_readonly",
            )
        }

        for user in users.values():
            self.assertTrue(user.is_active)
            self.assertTrue(user.check_password("shared-test-password"))

        self.assertTrue(users["test_superuser"].is_staff)
        self.assertTrue(users["test_superuser"].is_superuser)
        self.assertTrue(users["test_staff"].is_staff)
        self.assertFalse(users["test_staff"].is_superuser)
        self.assertEqual(users["test_staff"].get_all_permissions(), set())

        expected = {
            "test_editor": {
                "helloworld.view_company",
                "helloworld.submit_company_change",
                "helloworld.upload_company_data",
            },
            "test_reviewer": {
                "helloworld.view_company",
                "helloworld.review_pending_change",
                "helloworld.review_company_upload",
            },
            "test_readonly": {"helloworld.view_company"},
        }
        for username, permissions in expected.items():
            user = users[username]
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            self.assertEqual(user.get_all_permissions(), permissions)

    def test_rerun_repairs_flags_and_extra_permissions(self):
        """Restore the declared role state when local accounts drift."""
        self._seed()
        staff = get_user_model().objects.get(username="test_staff")
        staff.is_superuser = True
        staff.save(update_fields=["is_superuser"])
        staff.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="helloworld", codename="view_company"
            )
        )

        self._seed()

        staff.refresh_from_db()
        self.assertTrue(staff.is_staff)
        self.assertFalse(staff.is_superuser)
        self.assertEqual(staff.get_all_permissions(), set())
        self.assertFalse(staff.groups.exists())

    @override_settings(DEBUG=False)
    def test_seed_refuses_to_run_outside_debug_mode(self):
        """Prevent local credentials from being seeded in production mode."""
        with self.assertRaisesMessage(CommandError, "requires DEBUG=true"):
            call_command("seed_test_users", stdout=StringIO())
        self.assertFalse(get_user_model().objects.exists())
