from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("helloworld", "0018_pendingcompany_import_batch_id")]

    operations = [
        migrations.AlterModelOptions(
            name="pendingcompany",
            options={
                "db_table": "pending_company",
                "permissions": (
                    ("upload_company_data", "Can stage a spreadsheet upload"),
                    ("review_company_upload", "Can review a company upload"),
                ),
                "verbose_name": "Pending Company",
                "verbose_name_plural": "Pending Companies",
            },
        ),
        migrations.AlterModelOptions(
            name="pendingchanges",
            options={
                "db_table": "pending_change",
                "permissions": (
                    ("submit_company_change", "Can submit company changes"),
                    ("review_pending_change", "Can review pending company changes"),
                ),
                "verbose_name": "Pending Change",
                "verbose_name_plural": "Pending Changes",
            },
        ),
    ]
