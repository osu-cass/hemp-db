from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("helloworld", "0018_pendingcompany_import_batch_id")]

    operations = [
        migrations.AlterModelOptions(
            name="category",
            options={
                "db_table": "category",
                "permissions": (
                    (
                        "edit_metadata",
                        "Can create and delete HempDB reference-table values",
                    ),
                ),
                "verbose_name": "Category",
                "verbose_name_plural": "Categories",
            },
        ),
        migrations.AlterModelOptions(
            name="company",
            options={
                "db_table": "company",
                "indexes": [
                    models.Index(fields=["Name"], name="company_name_idx")
                ],
                "permissions": (
                    ("edit_companies", "Can submit company changes and manage uploads"),
                    ("review_company_changes", "Can review company changes"),
                ),
                "verbose_name": "Company",
                "verbose_name_plural": "Companies",
            },
        ),
    ]
