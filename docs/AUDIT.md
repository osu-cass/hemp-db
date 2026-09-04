# Auditing Database Entries

## Overview

The audit command runs through the terminal. It is implemented in
`helloworld/management/commands/audit.py`. Audit logs are written to
`AUDIT_LOG_DIR`, which defaults to
`helloworld/management/commands/auditlogs/` in local development.

Running `python manage.py audit` generates a CSV file named
`data_audit_YYYY-MM-DD.csv` for the current day. The CSV contains three columns:

1. **id**
    * The integer id of the company in the database
2. **company_name**
    * The name of the company in the database
3. **reasons**
    * A comma-separated list of reasons why the company was flagged as an erroneously-formatted item. The following reasons would be considered:
        - Entry is outdated, has not been updated in 6 months or more
        - Entry is missing 'Name' field (sql_alias: `Name`)
        - Entry is missing 'Status' field (sql_alias: `Status`)
        - Entry is missing 'Industry' field (sql_alias: `Industry`)
        - Entry is missing 'Stakeholder Category' field (sql_alias: `Category`)
        - Entry is missing 'Stakeholder Group' field (sql_alias: `stakeholderGroup`)
        - Entry is missing 'Development Stage' field (sql_alias: `Stage`)
        - Entry is missing 'Product Group' field (sql_alias: `productGroup`)
        - Entry is missing 'Description' field (sql_alias: `Description`)
        - Entry is missing 'Solution' field (sql_alias: `Solutions`)


## Running the Command

From the repository root, run:

```sh
python manage.py audit
```


## Limitations

### Performance
The command can take a long time because it queries related records for each
database entry. Django does not provide progress information for this queryset
work. See the [Django QuerySet documentation](https://docs.djangoproject.com/en/5.2/ref/models/querysets/).

### Logging
Audit logs are not removed automatically. Retention remains a separate cleanup
task for the audit-log directory.

### Affected Users
The scheduled audit job sends notifications to users with the **Admin** role.
The recipient logic is in `helloworld/cron.py`. On success, the notification
includes the generated CSV. Set `AUDIT_RECIPIENT` for an additional recipient;
it defaults to `EMAIL_USER`, which also supplies the sender address.
Developers can set `AUDIT_RECIPIENT` in `.env.docker` to test the
notification locally.
