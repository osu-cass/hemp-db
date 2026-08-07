"""Run the database audit and email its result."""

import logging
import os
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)
AUDITLOGS_PATH = Path(__file__).resolve().parent / "auditlogs"


def get_audit_recipients() -> list[str]:
    """Return unique administrator and configured audit email addresses."""
    admin_emails = list(
        User.objects.filter(groups__name="Admin")
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
    configured_recipient = os.getenv("AUDIT_RECIPIENT", "").strip()
    return list(
        dict.fromkeys(
            email for email in [*admin_emails, configured_recipient] if email
        )
    )


def get_latest_audit_file() -> Path | None:
    """Return the most recently modified audit CSV, if one exists."""
    audit_files = [path for path in AUDITLOGS_PATH.glob("*.csv") if path.is_file()]
    return max(audit_files, key=lambda path: path.stat().st_mtime, default=None)


class Command(BaseCommand):
    """Email the generated audit CSV to HempDB administrators."""

    help = "Run the database audit and email the result to administrators."

    def handle(self, *args, **options):
        """Run the audit and send a success or failure email."""
        recipients = get_audit_recipients()
        try:
            self.stdout.write("Audit notification job starting...")
            call_command("audit", stdout=self.stdout, stderr=self.stderr)

            audit_file = get_latest_audit_file()
            if audit_file is None:
                raise CommandError("Audit did not produce a CSV file.")

            file_date = datetime.fromtimestamp(audit_file.stat().st_mtime).date()
            self._send_success(audit_file, file_date, recipients)
            self.stdout.write(self.style.SUCCESS("Audit notification job complete."))
        except Exception as exc:
            logger.exception("Audit notification job failed")
            try:
                self._send_failure(exc, recipients)
            except Exception:
                logger.exception("Unable to send the audit failure email")

            if isinstance(exc, CommandError):
                raise
            raise CommandError("Audit notification job failed.") from exc

    @staticmethod
    def _send_success(audit_file: Path, file_date: date, recipients: list[str]):
        """Email the generated audit CSV."""
        email = EmailMessage(
            subject=f"[HempDB] Database Audit Log Generation {file_date}",
            body=(
                "The database audit completed successfully. "
                f"The generated report is attached as {audit_file.name}."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        with audit_file.open("rb") as report:
            email.attach(audit_file.name, report.read(), "text/csv")
        email.send()

    @staticmethod
    def _send_failure(exc: Exception, recipients: list[str]):
        """Email the audit failure details."""
        EmailMessage(
            subject=f"[HempDB] Database Audit Log Failure {timezone.localdate()}",
            body=f"The database audit failed:\n\n{exc}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        ).send()
