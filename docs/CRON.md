# Audit Notifications

HempDB provides a management command that runs the database audit and emails
the result. The application does not currently schedule this command; an
external scheduler can invoke it when automated execution is required.

## Manual Execution

From the project root, run:

```sh
python manage.py audit_email
```

In the local Compose stack, run:

```sh
docker compose exec app python manage.py audit_email
```

The command runs `python manage.py audit`, attaches the generated CSV to a
success email, and sends it to users in the `Admin` group plus the optional
`AUDIT_RECIPIENT` address. Email delivery uses the Django email settings.

If the audit or email delivery fails, the command logs the exception, attempts
to send a failure notice, and exits unsuccessfully. Use the command output and
application logs for debugging.

The previous `django-cron` integration is no longer used. Existing
`django_cron` database tables are left untouched, but HempDB no longer writes
execution records to them.
