from collections import Counter

from django.db import migrations, models

from helloworld.locations import US_COUNTRY, is_us_country, location_key, usps_state_code

# Country values on rows that are US companies by State in the imported data.
PLACEHOLDER_COUNTRIES = frozenset({"", "--", "1"})


def convert_us_states(apps, schema_editor):
    """Store USPS State codes and Country USA on US rows; report unmapped States."""
    for model_name in ("Company", "PendingCompany"):
        model = apps.get_model("helloworld", model_name)
        updates = []
        unmapped = Counter()
        for row in model.objects.only("pk", "Country", "State").iterator():
            if not row.State.strip() or not (
                is_us_country(row.Country)
                or location_key(row.Country) in PLACEHOLDER_COUNTRIES
            ):
                continue
            code = usps_state_code(row.State)
            if code is None:
                unmapped[(row.Country, row.State)] += 1
            elif (row.Country, row.State) != (US_COUNTRY, code):
                row.Country, row.State = US_COUNTRY, code
                updates.append(row)
        model.objects.bulk_update(updates, ["Country", "State"], batch_size=500)

        if updates or unmapped:
            print(f"\n  {model_name}: converted {len(updates)} rows to USPS State codes.")
            for (country, state), count in sorted(unmapped.items()):
                print(f"  {model_name}: left unmapped State {state!r} (Country {country!r}) on {count} rows.")


class Migration(migrations.Migration):

    dependencies = [
        ('helloworld', '0022_products_page_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='ZIP',
            field=models.CharField(blank=True, max_length=32, verbose_name='ZIP code'),
        ),
        migrations.AddField(
            model_name='pendingcompany',
            name='ZIP',
            field=models.CharField(blank=True, max_length=32, verbose_name='ZIP code'),
        ),
        migrations.RunPython(convert_us_states, migrations.RunPython.noop),
    ]
