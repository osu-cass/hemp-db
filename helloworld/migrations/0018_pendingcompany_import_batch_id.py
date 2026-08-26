from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('helloworld', '0001_squashed_0017_pendingchanges_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='pendingcompany',
            name='import_batch_id',
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
    ]
