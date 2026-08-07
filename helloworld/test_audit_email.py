"""Tests for the audit email management command."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import ANY, patch

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="hempdb@example.com",
)
class AuditEmailCommandTests(TestCase):
    """Verify success and failure notification behavior."""

    def setUp(self):
        """Create an administrator recipient."""
        admin_group = Group.objects.create(name="Admin")
        admin = User.objects.create_user(
            username="audit-admin",
            email="admin@example.com",
        )
        admin.groups.add(admin_group)

    @patch.dict(os.environ, {"AUDIT_RECIPIENT": "developer@example.com"})
    def test_success_email_attaches_the_audit_report(self):
        """Send the generated CSV to both configured recipient sources."""
        with TemporaryDirectory() as directory:
            report = Path(directory) / "data_audit.csv"
            report.write_text("id,company_name,reasons\n", encoding="utf-8")

            with (
                patch(
                    "helloworld.management.commands.audit_email.call_command"
                ) as audit_command,
                patch(
                    "helloworld.management.commands.audit_email.get_latest_audit_file",
                    return_value=report,
                ),
            ):
                call_command("audit_email")

        audit_command.assert_called_once_with(
            "audit",
            stdout=ANY,
            stderr=ANY,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertCountEqual(
            mail.outbox[0].to,
            ["admin@example.com", "developer@example.com"],
        )
        self.assertEqual(mail.outbox[0].attachments[0][0], "data_audit.csv")

    @patch.dict(os.environ, {"AUDIT_RECIPIENT": "developer@example.com"})
    def test_failure_email_preserves_a_nonzero_exit(self):
        """Send failure details and raise CommandError when the audit fails."""
        with patch(
            "helloworld.management.commands.audit_email.call_command",
            side_effect=RuntimeError("audit failed"),
        ):
            with self.assertRaisesMessage(
                CommandError,
                "Audit notification job failed.",
            ):
                call_command("audit_email")

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Database Audit Log Failure", mail.outbox[0].subject)
        self.assertIn("audit failed", mail.outbox[0].body)
