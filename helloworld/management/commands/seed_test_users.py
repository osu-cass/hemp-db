"""Seed local accounts for manual permission testing."""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

DEFAULT_DEV_PASSWORD = "hempdb-dev"

# Role groups created by migration 0021_role_groups.
RESEARCHER = "Researcher"
DATA_MANAGER = "Data Manager"
METADATA_EDITOR = "Metadata Editor"

TEST_USERS = {
    "test_superuser": {"is_staff": True, "is_superuser": True, "groups": ()},
    "test_staff": {"is_staff": True, "is_superuser": False, "groups": ()},
    "test_editor": {"is_staff": False, "is_superuser": False, "groups": (RESEARCHER,)},
    "test_reviewer": {"is_staff": False, "is_superuser": False, "groups": (DATA_MANAGER,)},
    "test_metadata_editor": {"is_staff": False, "is_superuser": False, "groups": (METADATA_EDITOR,)},
    "test_editor_metadata": {
        "is_staff": False, "is_superuser": False, "groups": (RESEARCHER, METADATA_EDITOR),
    },
    "test_editor_reviewer": {
        "is_staff": False, "is_superuser": False, "groups": (RESEARCHER, DATA_MANAGER),
    },
    "test_all_roles": {
        "is_staff": False,
        "is_superuser": False,
        "groups": (RESEARCHER, DATA_MANAGER, METADATA_EDITOR),
    },
    "test_readonly": {"is_staff": False, "is_superuser": False, "groups": ()},
}


class Command(BaseCommand):
    """Create local accounts for each role, role combination, and admin boundary."""

    help = "Seed local permission test users (DEBUG mode only)"

    @transaction.atomic
    def handle(self, *args, **options):
        """Reconcile local accounts, role memberships, flags, and passwords."""
        if not settings.DEBUG:
            raise CommandError(
                "seed_test_users is local-only and requires DEBUG=true."
            )

        password = os.getenv("DEV_SEED_PASSWORD", DEFAULT_DEV_PASSWORD)
        if not password:
            raise CommandError("DEV_SEED_PASSWORD cannot be empty.")

        role_groups = self._role_groups()
        user_model = get_user_model()
        users = []
        for username, access in TEST_USERS.items():
            user, _ = user_model.objects.get_or_create(username=username)
            user.is_active = True
            user.is_staff = access["is_staff"]
            user.is_superuser = access["is_superuser"]
            user.set_password(password)
            user.save(update_fields=[
                "is_active", "is_staff", "is_superuser", "password",
            ])
            user.user_permissions.clear()
            user.groups.set([role_groups[name] for name in access["groups"]])
            users.append(username)

        self.stdout.write(self.style.SUCCESS(
            "Local permission users ready:\n"
            f"  {', '.join(users)}\n"
            "  password: DEV_SEED_PASSWORD (default: hempdb-dev)\n"
            "  login: http://localhost:8000/user/login/"
        ))

    def _role_groups(self):
        """Return the migrated role groups by name."""
        names = {RESEARCHER, DATA_MANAGER, METADATA_EDITOR}
        role_groups = {group.name: group for group in Group.objects.filter(name__in=names)}
        missing = names - role_groups.keys()
        if missing:
            raise CommandError(
                "Missing role groups; run migrations first: " + ", ".join(sorted(missing))
            )
        return role_groups
