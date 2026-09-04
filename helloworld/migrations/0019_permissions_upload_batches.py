from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


def move_legacy_uploads(apps, schema_editor):
    """Attach legacy staged rows to one pending upload batch."""
    PendingCompany = apps.get_model("helloworld", "PendingCompany")
    CompanyUploadBatch = apps.get_model("helloworld", "CompanyUploadBatch")
    UploadIndex = apps.get_model("helloworld", "UploadIndex")
    legacy_ids = []
    for value in UploadIndex.objects.values_list("pendingID", flat=True):
        value = str(value).strip()
        if value.isdigit():
            legacy_ids.append(int(value))
    if not legacy_ids:
        return
    batch = CompanyUploadBatch.objects.create(
        original_filename="legacy staged upload",
        status="P",
    )
    PendingCompany.objects.filter(pk__in=legacy_ids).update(upload_batch=batch)


class Migration(migrations.Migration):
    dependencies = [("helloworld", "0018_pendingcompany_import_batch_id")]

    operations = [
        migrations.CreateModel(
            name="CompanyUploadBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("uploader", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="auth.user")),
                ("original_filename", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("P", "Pending"), ("A", "Approved"), ("C", "Canceled")], default="P", max_length=1)),
                ("review_mode", models.CharField(blank=True, choices=[("all", "All"), ("unique", "Unique")], max_length=10)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("reviewer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_company_uploads", to="auth.user")),
            ],
            options={"permissions": (("upload_company_data", "Can stage a spreadsheet upload"), ("review_company_upload", "Can review a company upload"))},
        ),
        migrations.AddField(
            model_name="pendingcompany", name="upload_batch",
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pending_companies", to="helloworld.companyuploadbatch"),
        ),
        migrations.AlterModelOptions(
            name="pendingchanges",
            options={"db_table": "pending_change", "permissions": (("submit_company_change", "Can submit company changes"), ("review_pending_change", "Can review pending company changes")), "verbose_name": "Pending Change", "verbose_name_plural": "Pending Changes"},
        ),
        migrations.RunPython(move_legacy_uploads, migrations.RunPython.noop),
        migrations.RemoveField(model_name="pendingcompany", name="import_batch_id"),
        migrations.DeleteModel(name="UploadIndex"),
    ]
