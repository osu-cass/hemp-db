"""Helpers shared by company workflow tests."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .models import Category, Company, Grower, Industry, Status
from .permissions import EDIT_COMPANIES, EDIT_METADATA, REVIEW_COMPANY_CHANGES


class CompanyWorkflowHelpers:
    """Create users, grant application permissions and build company form data."""

    def _user(self, username, **flags):
        """Create an active test user."""
        return get_user_model().objects.create_user(
            username=username,
            password="password",
            **flags,
        )

    def _grant(self, user, *permissions):
        """Grant application permissions from their declared owning models."""
        models = {
            EDIT_COMPANIES: Company,
            REVIEW_COMPANY_CHANGES: Company,
            EDIT_METADATA: Category,
        }
        user.user_permissions.add(
            *[
                Permission.objects.get(
                    content_type=ContentType.objects.get_for_model(models[permission]),
                    codename=permission.rsplit(".", 1)[1],
                )
                for permission in permissions
            ]
        )

    def _company_submission(self):
        """Return valid data for the company submission form."""
        status = Status.objects.create(status="Active")
        industry = Industry.objects.create(industry="Hemp")
        grower = Grower.objects.create(grower="Grower")
        return {
            "SrcKey": "",
            "Name": "Submitted company",
            "Address": "123 Main St",
            "Country": "USA",
            "Status": status.pk,
            "Industry": industry.pk,
            "Grower": grower.pk,
            "dateCreated": timezone.now().isoformat(),
        }
