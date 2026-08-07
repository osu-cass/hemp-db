# Auditing Database Entries

## Overview

The auditing functionality as of Spring 2025 is done through the terminal. The relevant files are under `helloworld/management/`:

Script: `audit.py`
List of past audit logs: `auditlogs/`

Running the command will generate a .csv file with the name: `data_audit_YYYY_MM_DD` with the current day in YYYY_MM_DD format. The .csv file will have three different columns:

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


## Running the Script

To execute the command in the terminal:

* Enter the root directory `hemp-db`
* Run `python manage.py audit`

Run `python manage.py audit_email` to generate the report and email it to the
configured recipients.


## Limitations

* Performance
The script takes a very long time to evaluate due to the volume of data in the database and querying relational items to each entry. It is difficult to get an idea of the progress for the script's completion due to the nature of querysets in Django: https://docs.djangoproject.com/en/5.2/ref/models/querysets/

* Logging
The audit logs will not be automatically removed. This is a future addition that would ideally be completed at the same time that automating the auditing process through CRON jobs would be implemented.

* Affected Users
The `audit_email` command sends success and failure notifications to people in
the **'Admin'** role. On success, the generated CSV is attached. Developers can
also set `AUDIT_RECIPIENT` in their environment to receive the notification.
