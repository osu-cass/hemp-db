from django.db import migrations

# Role groups from AB#4851. HempDB checks permissions, never these names.
# Keep "admin" out of the names: signals.py grants Staff for such groups.
ROLE_PERMISSIONS = {
    "Researcher": [("company", "edit_companies", "Can submit company changes and manage uploads")],
    "Data Manager": [("company", "review_company_changes", "Can review company changes")],
    "Metadata Editor": [("category", "edit_metadata", "Can create and delete HempDB reference-table values")],
}


def create_role_groups(apps, schema_editor):
    """Create each role group and add its permission without touching members."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for group_name, permissions in ROLE_PERMISSIONS.items():
        group, _created = Group.objects.get_or_create(name=group_name)
        for model, codename, name in permissions:
            # Permissions are normally created after migrate; create them here first.
            content_type, _created = ContentType.objects.get_or_create(
                app_label="helloworld", model=model
            )
            permission, _created = Permission.objects.get_or_create(
                content_type=content_type, codename=codename, defaults={"name": name}
            )
            group.permissions.add(permission)


def remove_role_groups(apps, schema_editor):
    """Remove the role groups."""
    apps.get_model("auth", "Group").objects.filter(name__in=ROLE_PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("helloworld", "0020_pendingchanges_upload_batch"),
    ]

    operations = [migrations.RunPython(create_role_groups, remove_role_groups)]
