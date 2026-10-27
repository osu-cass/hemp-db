"""Tests for local permission-account seeding."""

import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
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
                "test_superuser", "test_staff", "test_editor", "test_reviewer",
                "test_metadata_editor", "test_editor_metadata", "test_editor_reviewer",
                "test_all_roles", "test_readonly",
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
            "test_editor_metadata": {
                "helloworld.edit_companies",
                "helloworld.edit_metadata",
            },
            "test_editor_reviewer": {
                "helloworld.edit_companies",
                "helloworld.review_company_changes",
            },
            "test_all_roles": {
                "helloworld.edit_companies",
                "helloworld.review_company_changes",
                "helloworld.edit_metadata",
            },
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
        """Exercise the real upload and Changes gates with seeded accounts."""
        self._seed()
        for username, upload_status, changes_status in (
            ("test_superuser", 200, 200),
            ("test_staff", 403, 403),
            ("test_editor", 200, 200),
            ("test_reviewer", 403, 200),
            ("test_metadata_editor", 403, 403),
            ("test_editor_metadata", 200, 200),
            ("test_editor_reviewer", 200, 200),
            ("test_all_roles", 200, 200),
            ("test_readonly", 403, 403),
        ):
            with self.subTest(username=username):
                self.client.force_login(get_user_model().objects.get(username=username))
                self.assertEqual(
                    self.client.get(reverse("upload-wizard")).status_code, upload_status
                )
                self.assertEqual(
                    self.client.get(reverse("changes")).status_code, changes_status
                )

    def test_rerun_resets_role_memberships(self):
        """Restore the declared roles when a seeded account drifts."""
        self._seed()
        editor = get_user_model().objects.get(username="test_editor")
        editor.groups.add(Group.objects.get(name="Data Manager"))
        editor.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="helloworld", codename="edit_metadata"
            )
        )

        self._seed()

        editor = get_user_model().objects.get(pk=editor.pk)
        self.assertEqual(list(editor.groups.values_list("name", flat=True)), ["Researcher"])
        self.assertEqual(editor.get_all_permissions(), {"helloworld.edit_companies"})

    def test_seed_requires_the_migrated_role_groups(self):
        """Fail clearly instead of creating its own role groups."""
        Group.objects.filter(name="Data Manager").delete()

        with self.assertRaisesMessage(CommandError, "run migrations first: Data Manager"):
            self._seed()
        self.assertFalse(Group.objects.filter(name="Data Manager").exists())

    @override_settings(DEBUG=False)
    def test_seed_refuses_to_run_outside_debug_mode(self):
        """Prevent local credentials from being seeded in production mode."""
        with self.assertRaisesMessage(CommandError, "requires DEBUG=true"):
            call_command("seed_test_users", stdout=StringIO())
        self.assertFalse(get_user_model().objects.exists())
