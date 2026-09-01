"""Report HempDB access flags and effective feature permissions."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from helloworld.permissions import FEATURE_PERMISSIONS, effective_feature_permissions


class Command(BaseCommand):
    """Print a read-only access report for every user."""

    help = "Report user flags, groups, and effective HempDB feature permissions"

    def handle(self, *args, **options):
        """Write the access report without changing database state."""
        users = []
        policy_violations = []
        for user in get_user_model().objects.prefetch_related("groups").order_by("username"):
            row = {
                "username": user.get_username(),
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "groups": sorted(user.groups.values_list("name", flat=True)),
                "permissions": effective_feature_permissions(user),
            }
            users.append(row)
            if user.is_staff and not user.is_superuser:
                policy_violations.append(user.get_username())

        self.stdout.write(json.dumps({
            "feature_permissions": list(FEATURE_PERMISSIONS),
            "users": users,
            "policy_violations": policy_violations,
        }, sort_keys=True))
