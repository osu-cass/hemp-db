"""Seed local accounts for manual permission testing."""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

DEFAULT_DEV_PASSWORD = "hempdb-dev"

# Group names are local labels only; authorization checks permission codenames.
LOCAL_GROUPS = {
    "editor": ("HempDB Local Editor", (
        "view_company", "submit_company_change", "upload_company_data",
    )),
    "reviewer": ("HempDB Local Data Manager", (
        "view_company", "review_pending_change", "review_company_upload",
    )),
    "readonly": ("HempDB Local Read Only", ("view_company",)),
}

TEST_USERS = {
    "test_superuser": {"is_staff": True, "is_superuser": True, "role": None},
    "test_staff": {"is_staff": True, "is_superuser": False, "role": None},
    "test_editor": {"is_staff": False, "is_superuser": False, "role": "editor"},
    "test_reviewer": {"is_staff": False, "is_superuser": False, "role": "reviewer"},
    "test_readonly": {"is_staff": False, "is_superuser": False, "role": "readonly"},
}


class Command(BaseCommand):
    """Create the five local permission-test accounts."""

    help = "Seed local permission test users (DEBUG mode only)"

    @transaction.atomic
    def handle(self, *args, **options):
        """Reconcile local accounts, groups, flags, and passwords."""
        if not settings.DEBUG:
            raise CommandError(
                "seed_test_users is local-only and requires DEBUG=true."
            )

        password = os.getenv("DEV_SEED_PASSWORD", DEFAULT_DEV_PASSWORD)
        if not password:
            raise CommandError("DEV_SEED_PASSWORD cannot be empty.")

        role_groups = self._seed_role_groups()
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
            role = access["role"]
            user.groups.set([role_groups[role]] if role else [])
            users.append(username)

        self.stdout.write(self.style.SUCCESS(
            "Local permission users ready:\n"
            f"  {', '.join(users)}\n"
            "  password: DEV_SEED_PASSWORD (default: hempdb-dev)\n"
            "  login: http://localhost:8000/user/login/"
        ))

    def _seed_role_groups(self):
        """Create local groups with their exact permission sets."""
        role_groups = {}
        for role, (group_name, codenames) in LOCAL_GROUPS.items():
            permissions = Permission.objects.filter(
                content_type__app_label="helloworld",
                codename__in=codenames,
            )
            found = set(permissions.values_list("codename", flat=True))
            missing = set(codenames) - found
            if missing:
                raise CommandError(
                    "Missing permissions; run migrations first: "
                    + ", ".join(sorted(missing))
                )
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.set(permissions)
            role_groups[role] = group
        return role_groups
