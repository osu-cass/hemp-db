import logging
from pathlib import Path
from datetime import datetime
from django.conf import settings
from django_cron import CronJobBase, Schedule
from helloworld.management.commands.audit import Command as Audit
from django.core.mail import EmailMessage
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
AUDITLOGS_PATH = Path(settings.AUDIT_LOG_DIR)


def get_audit_file():
    assert(BASE_DIR.exists())
    assert(AUDITLOGS_PATH.exists())

    csv_files = list(file for file in AUDITLOGS_PATH.iterdir())

    if not csv_files: # no csv files in the auditlogs
        return None, None

    latest_file = max(csv_files, key=lambda f: f.stat().st_mtime) # pulling metadata from audit log files for time created
    modified_time = datetime.fromtimestamp(latest_file.stat().st_mtime)

    return latest_file.name, modified_time.date()



class CronAudit(CronJobBase):
    RUN_EVERY_MINS = 30240 # 30240 = 3 weeks worth of minutes (NOT CURRENTLY IN USE)
    # Schedule is necessary for the cron job to be properly recognized
    # Future development would involve using some third party service to trigger this on a regular basis,
    #    but currently it is serving as a placeholder to fill a requirement of Django's basic cron job recognition
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'helloworld.CronAudit'

    def do(self):
        """Run the audit and email the resulting report."""
        logger.info("Cron Audit Job Starting...")
        admin_emails = list(
            User.objects.filter(is_active=True, is_superuser=True)
            .exclude(email="")
            .values_list("email", flat=True)
            .distinct()
        )

        EMAIL_USER = settings.EMAIL_HOST_USER
        AUDIT_RECIPIENT = settings.AUDIT_RECIPIENT
        recipients = list(dict.fromkeys(
            admin_emails + ([AUDIT_RECIPIENT] if AUDIT_RECIPIENT else [])
        ))
        filedate = datetime.now().date()

        try:
            audit = Audit()
            audit.handle()
            logger.info("Audit Complete")
            auditlog, filedate = get_audit_file()

            if not auditlog or not filedate:
                raise Exception("Invalid auditlog file found, please reference the directory you are trying to access to resolve this issue.")

            file_path = AUDITLOGS_PATH / auditlog

            ##
            ## Note: Specify list of people to receive the email report under 'to' parameter list
            ##
            with open(file_path, 'rb') as file:
                email = EmailMessage(
                    subject=f"[HempDB] Database Audit Log Generation {filedate}",
                    body=f"The Database Audit job was successful, the new file created is attached to this message with the name: {auditlog}. The file is stored in the audit log directory: {AUDITLOGS_PATH}.",
                    from_email=EMAIL_USER,
                    to=recipients
                )

                email.attach(auditlog, file.read(), 'text/csv')
                email.send()
            



        except Exception as e:
            logger.exception("Auditing failed", exc_info=True)
            email = EmailMessage(
                subject=f"[HempDB] Database Audit Log Failure {filedate}",
                body=f"The Database Audit job failed. Please alert developers to the status of the audit generation. The following error is:\n\n\n{e}",
                from_email=EMAIL_USER,
                to=recipients
            )
            email.send()

    def on_failure(self, exc):
        logger.exception(f"Audit Failed: {exc}")
