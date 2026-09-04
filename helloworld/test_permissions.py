"""Permission and workflow tests for feature-gated HempDB actions."""

import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.urls import reverse

from .models import (
    Company,
    CompanyUploadBatch,
    Grower,
    Industry,
    PendingChanges,
    PendingCompany,
    Status,
)
from .notifications import email_admins
from .permissions import FEATURE_PERMISSIONS
from .views import UPLOAD_WIZARD_PAGE_SIZE


class PermissionWorkflowTests(TestCase):
    """Cover feature roles, workflow ownership, and admin access."""

    def setUp(self):
        """Create users representing each documented access level."""
        self.researcher = self._user("researcher")
        self.manager = self._user("manager")
        self.combined = self._user("combined")
        self.read_only = self._user("read-only")
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
            "upload_company_data": CompanyUploadBatch,
            "review_company_upload": CompanyUploadBatch,
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

        self.client.force_login(self.read_only)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload")).status_code, 403)

    def test_group_names_do_not_authorize_or_change_staff_flags(self):
        """Renaming an operational group does not affect feature access."""
        group = Group.objects.create(name="Admin legacy group")
        group.permissions.set(
            Permission.objects.filter(codename="review_pending_change")
        )
        self.read_only.user_permissions.clear()
        self.read_only.groups.add(group)
        self.read_only.refresh_from_db()
        self.assertFalse(self.read_only.is_staff)
        self.client.force_login(self.read_only)
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
        self.client.force_login(self.read_only)
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

    @patch("helloworld.signals.cache.delete")
    def test_pending_approval_is_post_only_locked_and_single_use(self, cache_delete):
        """A reviewed proposal cannot be processed a second time."""
        change = self._pending_change()
        url = reverse("company-pending-approve", args=[change.pk])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 409)
        self.assertEqual(
            PendingChanges.objects.get(pk=change.pk).status,
            PendingChanges.PendingStatus.APPROVED,
        )
        self.assertEqual(Company.objects.filter(Name="Pending company").count(), 1)

    def test_pending_approval_requires_csrf(self):
        """Reject an approval request that does not pass CSRF middleware."""
        change = self._pending_change()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("company-pending-approve", args=[change.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            PendingChanges.objects.get(pk=change.pk).status,
            PendingChanges.PendingStatus.PENDING,
        )

    def test_deletion_approval_keeps_decision_for_conflict_detection(self):
        """Preserve an approved deletion record so duplicate requests conflict."""
        company = Company.objects.create(
            SrcKey="", Name="Delete me", Address="", Country="USA"
        )
        change = PendingChanges.objects.create(
            company=company, author=self.researcher, changeType="deletion"
        )
        url = reverse("company-pending-approve", args=[change.pk])
        self.client.force_login(self.manager)

        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 409)
        change.refresh_from_db()
        self.assertIsNone(change.company_id)

    def test_combined_user_can_approve_their_own_pending_change(self):
        """A user with both capabilities may review their own proposal."""
        change = self._pending_change(author=self.combined)
        self.client.force_login(self.combined)

        response = self.client.post(
            reverse("company-pending-approve", args=[change.pk])
        )

        self.assertEqual(response.status_code, 302)
        change.refresh_from_db()
        self.assertEqual(change.status, PendingChanges.PendingStatus.APPROVED)
        self.assertTrue(Company.objects.filter(Name="Pending company").exists())

    def test_approved_deletion_history_can_be_viewed(self):
        """An approved deletion remains a safe, viewable history record."""
        company = Company.objects.create(
            SrcKey="", Name="Deleted company", Address="", Country="USA"
        )
        change = PendingChanges.objects.create(
            company=company, author=self.researcher, changeType="deletion"
        )
        self.client.force_login(self.manager)
        self.client.post(reverse("company-pending-approve", args=[change.pk]))

        self.client.force_login(self.researcher)
        response = self.client.get(
            reverse("company-view-pending", args=[change.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Change Type: deletion")

    def test_admin_uses_standard_active_staff_access(self):
        """Active Staff users enter Admin without becoming superusers."""
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

        company_url = reverse("admin:helloworld_company_changelist")
        self.assertEqual(self.client.get(company_url).status_code, 403)
        self.staff.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Company),
                codename="view_company",
            )
        )
        self.assertEqual(self.client.get(company_url).status_code, 200)

    def test_admin_rejects_inactive_staff_and_active_nonstaff(self):
        """Both active and Staff are required for Django Admin."""
        inactive_staff = self._user("inactive-staff", is_active=False, is_staff=True)

        self.client.force_login(inactive_staff)
        self.assertRedirects(
            self.client.get("/admin/"),
            "/admin/login/?next=/admin/",
            fetch_redirect_response=False,
        )

        for feature_user in (self.researcher, self.manager):
            self.assertFalse(feature_user.is_staff)
            self.client.force_login(feature_user)
            self.assertRedirects(
                self.client.get("/admin/"),
                "/admin/login/?next=/admin/",
                fetch_redirect_response=False,
            )

    def test_active_staff_superuser_has_unrestricted_admin_access(self):
        """An active Staff superuser retains Django's implicit permissions."""
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(
            self.client.get(reverse("admin:helloworld_company_changelist")).status_code,
            200,
        )


class UploadBatchTests(TestCase):
    """Verify ownership and isolation of spreadsheet upload batches."""

    def setUp(self):
        """Create a researcher and data manager."""
        self.researcher = get_user_model().objects.create_user(username="researcher")
        self.manager = get_user_model().objects.create_user(username="manager")
        self.combined = get_user_model().objects.create_user(username="combined")
        self._grant(self.researcher, "upload_company_data")
        self._grant(self.manager, "review_company_upload")
        self._grant(self.combined, "upload_company_data")
        self._grant(self.combined, "review_company_upload")

    def _grant(self, user, codename):
        """Grant one upload feature permission."""
        permission = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(CompanyUploadBatch),
            codename=codename,
        )
        user.user_permissions.add(permission)

    def _batch(self, uploader, filename, name):
        """Create a batch containing one staged row."""
        batch = CompanyUploadBatch.objects.create(
            uploader=uploader, original_filename=filename
        )
        PendingCompany.objects.create(
            upload_batch=batch, SrcKey="", Address="", Name=name, Country="USA"
        )
        return batch

    def test_researchers_see_only_their_batches_and_managers_see_all(self):
        """Batch list visibility is scoped by the uploader unless reviewing."""
        own = self._batch(self.researcher, "own.csv", "Own row")
        other = self._batch(
            get_user_model().objects.create_user(username="other"),
            "other.csv",
            "Other row",
        )
        self.client.force_login(self.researcher)
        response = self.client.get(reverse("upload-wizard"))
        self.assertContains(response, own.original_filename)
        self.assertNotContains(response, other.original_filename)

        self.client.force_login(self.manager)
        response = self.client.get(reverse("upload-wizard"))
        self.assertContains(response, own.original_filename)
        self.assertContains(response, other.original_filename)

    def test_combined_users_see_own_history_and_all_pending_batches(self):
        """Combined users see their history and every pending batch."""
        own_pending = self._batch(self.combined, "own-pending.csv", "Own pending")
        own_approved = self._batch(
            self.combined, "own-approved.csv", "Own approved"
        )
        own_canceled = self._batch(
            self.combined, "own-canceled.csv", "Own canceled"
        )
        other_pending = self._batch(
            get_user_model().objects.create_user(username="other"),
            "other-pending.csv",
            "Other pending",
        )
        other_approved = self._batch(
            get_user_model().objects.create_user(username="completed"),
            "other-approved.csv",
            "Other approved",
        )
        own_approved.status = CompanyUploadBatch.Status.APPROVED
        own_approved.save(update_fields=["status"])
        own_canceled.status = CompanyUploadBatch.Status.CANCELED
        own_canceled.save(update_fields=["status"])
        other_approved.status = CompanyUploadBatch.Status.APPROVED
        other_approved.save(update_fields=["status"])

        self.client.force_login(self.combined)
        response = self.client.get(reverse("upload-wizard"))

        for filename in (
            own_pending.original_filename,
            own_approved.original_filename,
            own_canceled.original_filename,
            other_pending.original_filename,
        ):
            self.assertContains(response, filename)
        self.assertNotContains(response, other_approved.original_filename)

    def test_manager_finalization_is_scoped_and_double_submit_conflicts(self):
        """Approving one batch does not consume another batch."""
        first = self._batch(self.researcher, "first.csv", "First row")
        second = self._batch(self.researcher, "second.csv", "Second row")
        self.client.force_login(self.manager)
        url = reverse("upload-batch", args=[first.pk])
        self.assertEqual(self.client.post(url, {"add-all": "1"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"add-all": "1"}).status_code, 409)
        self.assertEqual(
            CompanyUploadBatch.objects.get(pk=first.pk).status,
            CompanyUploadBatch.Status.APPROVED,
        )
        self.assertEqual(
            PendingCompany.objects.filter(upload_batch=second).count(), 1
        )

    def test_batch_finalization_requires_csrf(self):
        """Reject upload finalization without a valid CSRF token."""
        batch = self._batch(self.researcher, "csrf.csv", "CSRF row")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)

        response = client.post(
            reverse("upload-batch", args=[batch.pk]), {"add-all": "1"}
        )

        self.assertEqual(response.status_code, 403)
        batch.refresh_from_db()
        self.assertEqual(batch.status, CompanyUploadBatch.Status.PENDING)
        self.assertEqual(batch.pending_companies.count(), 1)

    def test_batch_detail_paginates_and_marks_duplicates_with_bounded_queries(self):
        """Preview page two marks duplicates without one query per staged row."""
        batch = CompanyUploadBatch.objects.create(
            uploader=self.researcher, original_filename="large.csv"
        )
        names = [f"Batch company {index}" for index in range(UPLOAD_WIZARD_PAGE_SIZE + 1)]
        PendingCompany.objects.bulk_create(
            [
                PendingCompany(
                    upload_batch=batch,
                    SrcKey="",
                    Address="",
                    Name=name,
                    Country="USA",
                )
                for name in names
            ]
        )
        Company.objects.create(
            SrcKey="", Name=names[-1], Address="", Country="USA"
        )

        self.client.force_login(self.researcher)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("upload-batch", args=[batch.pk]) + "?page=2"
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, names[-1])
        self.assertContains(response, "table-danger")
        self.assertContains(response, "True")
        self.assertLessEqual(len(queries), 12)

    def test_researcher_stages_a_named_batch_without_global_index_rows(self):
        """A spreadsheet upload records ownership and batch identity."""
        from .models import Industry, Grower, Status

        status = Status.objects.create(status="Active")
        industry = Industry.objects.create(industry="Hemp")
        grower = Grower.objects.create(grower="Grower")
        upload = SimpleUploadedFile(
            "companies.csv",
            (
                "Name,Country,Status,Industry,Grower\n"
                f"Acme,USA,{status.pk},{industry.pk},{grower.pk}\n"
            ).encode(),
            content_type="text/csv",
        )
        self.client.force_login(self.researcher)
        response = self.client.post(reverse("upload"), {"file": upload})

        self.assertEqual(response.status_code, 302)
        batch = CompanyUploadBatch.objects.get(original_filename="companies.csv")
        self.assertEqual(batch.uploader, self.researcher)
        self.assertEqual(batch.pending_companies.count(), 1)


class AccessReportingTests(TestCase):
    """Verify notification recipients and read-only audit reporting."""

    def test_notifications_use_effective_review_permission(self):
        """Only active reviewers and active superusers receive notifications."""
        reviewer = get_user_model().objects.create_user(
            username="reviewer", email="reviewer@example.com"
        )
        superuser = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="password"
        )
        researcher = get_user_model().objects.create_user(
            username="researcher", email="researcher@example.com"
        )
        permission = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(PendingChanges),
            codename="review_pending_change",
        )
        reviewer.user_permissions.add(permission)

        with patch("helloworld.notifications.settings.DEBUG", True), patch(
            "helloworld.notifications.send_mail"
        ) as send_mail:
            email_admins("created", "Acme", 1, "localhost")

        recipients = send_mail.call_args.kwargs["recipient_list"]
        self.assertEqual(set(recipients), {reviewer.email, superuser.email})
        self.assertNotIn(researcher.email, recipients)

    def test_audit_access_is_read_only_and_reports_access_state(self):
        """The audit command reports flags without mutating users or groups."""
        staff = get_user_model().objects.create_user(username="legacy", is_staff=True)
        before = list(
            get_user_model().objects.values_list(
                "username", "is_active", "is_staff", "is_superuser"
            )
        )
        output = StringIO()
        call_command("audit_access", stdout=output)
        report = json.loads(output.getvalue())
        after = list(
            get_user_model().objects.values_list(
                "username", "is_active", "is_staff", "is_superuser"
            )
        )

        self.assertEqual(before, after)
        staff_row = next(
            user for user in report["users"] if user["username"] == staff.username
        )
        self.assertTrue(staff_row["is_staff"])
        self.assertFalse(staff_row["is_superuser"])
        self.assertEqual(staff_row["groups"], [])
        self.assertEqual(
            staff_row["permissions"],
            {permission: False for permission in FEATURE_PERMISSIONS},
        )
        self.assertNotIn("policy_violations", report)
        self.assertEqual(
            sorted(report["feature_permissions"]), sorted(FEATURE_PERMISSIONS)
        )
