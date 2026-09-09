"""Permission and workflow tests for feature-gated HempDB actions."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from .models import (
    Grower,
    Industry,
    PendingChanges,
    PendingCompany,
    Status,
)
from .permissions import FEATURE_PERMISSIONS


class PermissionWorkflowTests(TestCase):
    """Cover feature permission enforcement."""

    def setUp(self):
        """Create users with representative permission combinations."""
        self.researcher = self._user("researcher")
        self.manager = self._user("manager")
        self.combined = self._user("combined")
        self.unprivileged = self._user("unprivileged")
        self.staff = self._user("staff", is_staff=True)
        self.superuser = self._user("superuser", is_staff=True, is_superuser=True)
        self._grant(self.researcher, "submit_company_change", "upload_company_data")
        self._grant(self.manager, "review_pending_change", "review_company_upload")
        self._grant(self.combined, *[permission.rsplit(".", 1)[1] for permission in FEATURE_PERMISSIONS])

    def _user(self, username, **flags):
        """Create an active test user."""
        return get_user_model().objects.create_user(
            username=username, password="password", **flags
        )

    def _grant(self, user, *codenames):
        """Grant feature permissions from their owning model content types."""
        models = {
            "submit_company_change": PendingChanges,
            "review_pending_change": PendingChanges,
            "upload_company_data": PendingCompany,
            "review_company_upload": PendingCompany,
        }
        permissions = [
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(models[codename]),
                codename=codename,
            )
            for codename in codenames
        ]
        user.user_permissions.add(*permissions)

    def _pending_change(self, author=None):
        """Create a minimal pending create proposal."""
        pending = PendingCompany.objects.create(
            SrcKey="", Name="Pending company", Address="", Country="USA"
        )
        return PendingChanges.objects.create(
            pending_company=pending,
            author=author or self.researcher,
            changeType="create",
        )

    def test_roles_gate_review_and_upload_pages(self):
        """Research and review permissions are independent capabilities."""
        self.client.force_login(self.researcher)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("upload")).status_code, 405)

        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 200)

        self.client.force_login(self.combined)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 200)

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)

        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 200)

        self.client.force_login(self.unprivileged)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload")).status_code, 403)

    def test_group_names_do_not_authorize_features(self):
        """Only assigned permissions grant feature access."""
        group = Group.objects.create(name="Reviewers")
        group.permissions.set(
            Permission.objects.filter(codename="review_pending_change")
        )
        self.unprivileged.user_permissions.clear()
        self.unprivileged.groups.add(group)
        self.client.force_login(self.unprivileged)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)

        group.name = "renamed without a role meaning"
        group.save()
        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)

    def test_pending_detail_is_author_or_reviewer_visible(self):
        """Authors can inspect their own proposal and reviewers can inspect all."""
        change = self._pending_change()
        url = reverse("company-view-pending", args=[change.pk])

        self.client.force_login(self.researcher)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.unprivileged)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approve")

        self.client.force_login(self.researcher)
        self.assertNotContains(self.client.get(url), "Approve")

    @patch("helloworld.views.email_admins")
    @patch("helloworld.views.geocode_location", return_value=(None, None))
    def test_researcher_can_submit_a_company_change(self, _geocode, _email_admins):
        """A researcher can submit a new company through the companies form."""
        status = Status.objects.create(status="Active")
        industry = Industry.objects.create(industry="Hemp")
        grower = Grower.objects.create(grower="Grower")
        self.client.force_login(self.researcher)
        response = self.client.post(
            reverse("companies"),
            {
                "SrcKey": "",
                "Name": "Researcher company",
                "Address": "123 Main St",
                "Country": "USA",
                "Status": status.pk,
                "Industry": industry.pk,
                "Grower": grower.pk,
                "dateCreated": timezone.now().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        change = PendingChanges.objects.get(author=self.researcher)
        self.assertEqual(change.changeType, "create")
        self.assertEqual(change.pending_company.Name, "Researcher company")

    def test_navbar_uses_feature_permissions(self):
        """Feature links use permissions, while Admin follows the Staff flag."""
        self.client.force_login(self.researcher)
        response = self.client.get("/")
        self.assertContains(response, "/upload_wizard")
        self.assertNotContains(response, "/changes")
        self.assertNotContains(response, "/admin")

        self.client.force_login(self.manager)
        response = self.client.get("/")
        self.assertContains(response, "/changes")
        self.assertNotContains(response, "/admin")

        self.client.force_login(self.staff)
        response = self.client.get("/")
        self.assertNotContains(response, "/changes")
        self.assertContains(response, "/admin")
