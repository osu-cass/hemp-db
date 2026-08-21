# Cron Jobs

### This document contains information on the Cron Job configuration and limitations for HempDB

Cron jobs are meant to streamline simple, repetitive tasks. They are set up using `django-cron` (https://django-cron.readthedocs.io/en/latest/).

The deployment stack ships a one-shot `cron` service under the `operations`
Compose profile that runs `python manage.py runcrons`. The host scheduler (a
crontab entry or systemd timer) runs it on the desired schedule; see
[PRODUCTION.md](PRODUCTION.md) for the exact command.

## Manual Execution

In local development, run the jobs inside the app container:

```sh
docker compose exec app python manage.py runcrons
```

In a deployed stack, run the `cron` service through the `operations` profile
as shown in [PRODUCTION.md](PRODUCTION.md).

Specify `--force` if re-executing a cron job after edits were recently made to it. Django will cache the most recent execution so it is necessary to force the application to look for the updated script. (https://django-cron.readthedocs.io/en/latest/installation.html)

A cron job will show up successful with a [✔] and unsuccessful with a [✘]

### Successful Output Example:
(Text generated here originates from the file `cron.py` and the audit script `audit.py`)
```
Running Crons
========================================
Running cron: CronAudit code helloworld.CronAudit
Cron Audit Job Starting...
Audit Complete
[✔] helloworld.CronAudit
```

### Unsuccessful Output Example:

```
Running Crons
========================================
[✘] helloworld.CronAudit
```


## Debugging

The cron jobs use `logging` as a method to output text and track completions. The logging configuration is listed in `settings.py` under `LOGGING`. If a cron job is not executing and it is unable to provide a traceback:

1. Open the django shell using `docker compose exec app python manage.py shell`
2. Type in the following:
```

from django_cron.models import CronJobLog
CronJobLog.objects.all() # grabs a history of all cron job executions

last = CronJobLog.objects.latest('started_at') # to find the most recent failed job traceback
print(last.message)

```

## Active Cron Jobs

# CronAudit

Execute the audit management command to generate a `.csv` file with database entries that are erroneous or old. More info in `hemp-db/helloworld/management/commands/audit.py`

Future goal to automatically email the `.csv` list to admins once the cron job is successful, and email an error message if the job should fail.
