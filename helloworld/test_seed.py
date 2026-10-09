"""Tests for local permission-account seeding."""

import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

@override_settings(DEBUG=True)
class SeedUsersTests(TestCase):
    """Verify local accounts and their permission boundaries."""

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
                "test_reviewer", "test_metadata_editor", "test_readonly",
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
                "helloworld.edit_companies",
            },
            "test_reviewer": {
                "helloworld.review_company_changes",
            },
            "test_metadata_editor": {"helloworld.edit_metadata"},
            "test_readonly": set(),
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

    def test_seeded_accounts_can_access_their_workflows(self):
        """Exercise the real upload and review gates with seeded accounts."""
        self._seed()
        for username, upload_status, review_status in (
            ("test_superuser", 200, 200),
            ("test_staff", 403, 403),
            ("test_editor", 200, 403),
            ("test_reviewer", 403, 200),
            ("test_metadata_editor", 403, 403),
            ("test_readonly", 403, 403),
        ):
            with self.subTest(username=username):
                self.client.force_login(get_user_model().objects.get(username=username))
                self.assertEqual(
                    self.client.get(reverse("upload-wizard")).status_code, upload_status
                )
                self.assertEqual(
                    self.client.get(reverse("changes")).status_code, review_status
                )

    def test_rerun_replaces_legacy_group_grants(self):
        """Replace old permission grants on existing seeded groups."""
        self._seed()
        editor = get_user_model().objects.get(username="test_editor")
        legacy, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get(app_label="helloworld", model="company"),
            codename="submit_company_change",
            defaults={"name": "Legacy submission permission"},
        )
        editor.groups.get().permissions.set([legacy])
        editor.user_permissions.add(legacy)
        self._seed()
        editor = get_user_model().objects.get(pk=editor.pk)
        self.assertEqual(editor.get_all_permissions(), {"helloworld.edit_companies"})

    @override_settings(DEBUG=False)
    def test_seed_refuses_to_run_outside_debug_mode(self):
        """Prevent local credentials from being seeded in production mode."""
        with self.assertRaisesMessage(CommandError, "requires DEBUG=true"):
            call_command("seed_test_users", stdout=StringIO())
        self.assertFalse(get_user_model().objects.exists())
