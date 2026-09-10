"""Permission checks for HempDB application workflows."""

from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Category,
    Company,
    Grower,
    Industry,
    PendingChanges,
    PendingCompany,
    ProductGroup,
    Solution,
    Stage,
    Status,
    UploadIndex,
    stakeholderGroups,
)
from .notifications import email_admins
from .permissions import (
    EDIT_COMPANIES,
    EDIT_METADATA,
    REVIEW_COMPANY_CHANGES,
    users_with_application_permission,
)


class PermissionWorkflowTests(TestCase):
    """Cover the application permission boundaries."""

    reference_tables = (
        ("categories", "export-categories", "remove_categories", Category, {"category": "Category"}),
        ("solutions", "export-solutions", "remove_solutions", Solution, {"solution": "Solution"}),
        (
            "StakeholderGroups",
            "export-stakeholder_groups",
            "remove_stakeholder_groups",
            stakeholderGroups,
            {"stakeholderGroup": "Stakeholder group"},
        ),
        ("stages", "export-stages", "remove_stages", Stage, {"stage": "Stage"}),
        (
            "productGroups",
            "export-product_groups",
            "remove_product_group",
            ProductGroup,
            {"productGroup": "Product group"},
        ),
        ("status", "export-status", "remove_status", Status, {"status": "Status"}),
        ("grower", "export-grower", "remove_grower", Grower, {"grower": "Grower"}),
        ("industry", "export-industry", "remove_industry", Industry, {"industry": "Industry"}),
    )

    def setUp(self):
        """Create users with each application permission combination."""
        self.editor = self._user("editor")
        self.reviewer = self._user("reviewer")
        self.metadata_editor = self._user("metadata-editor")
        self.edit_reviewer = self._user("edit-reviewer")
        self.edit_metadata_editor = self._user("edit-metadata-editor")
        self.review_metadata_editor = self._user("review-metadata-editor")
        self.combined = self._user("combined")
        self.unprivileged = self._user("unprivileged")
        self.staff = self._user("staff", is_staff=True)
        self.superuser = self._user("superuser", is_staff=True, is_superuser=True)
        self.legacy = self._user("legacy")
        self._grant(self.editor, EDIT_COMPANIES)
        self._grant(self.reviewer, REVIEW_COMPANY_CHANGES)
        self._grant(self.metadata_editor, EDIT_METADATA)
        self._grant(self.edit_reviewer, EDIT_COMPANIES, REVIEW_COMPANY_CHANGES)
        self._grant(self.edit_metadata_editor, EDIT_COMPANIES, EDIT_METADATA)
        self._grant(
            self.review_metadata_editor, REVIEW_COMPANY_CHANGES, EDIT_METADATA
        )
        self._grant(
            self.combined,
            EDIT_COMPANIES,
            REVIEW_COMPANY_CHANGES,
            EDIT_METADATA,
        )

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

    def _pending_change(self, author=None, name="Pending company"):
        """Create a minimal pending company proposal."""
        pending = PendingCompany.objects.create(
            SrcKey="",
            Name=name,
            Address="",
            Country="USA",
        )
        return PendingChanges.objects.create(
            pending_company=pending,
            author=author or self.editor,
            changeType="create",
        )

    def _reference_data(self, model, data):
        """Return valid POST data for a reference-table form."""
        if model is stakeholderGroups:
            data = {
                **data,
                "category": Category.objects.create(category="Reference category").pk,
            }
        return data

    def _legacy_permission(self, codename):
        """Create a historical permission record retained from version 0019."""
        owners = {
            "submit_company_change": PendingChanges,
            "review_pending_change": PendingChanges,
            "upload_company_data": PendingCompany,
            "review_company_upload": PendingCompany,
        }
        return Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(owners[codename]),
            codename=codename,
            defaults={"name": f"Legacy {codename}"},
        )[0]

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

    def _upload_file(self):
        """Return a CSV upload with valid reference-table IDs."""
        status = Status.objects.create(status="Upload active")
        industry = Industry.objects.create(industry="Upload hemp")
        grower = Grower.objects.create(grower="Upload grower")
        return SimpleUploadedFile(
            "companies.csv",
            (
                "Name,Country,Status,Industry,Grower\n"
                f"Staged company,USA,{status.pk},{industry.pk},{grower.pk}\n"
            ).encode(),
            content_type="text/csv",
        )

    def test_signed_out_users_redirect_from_every_private_area(self):
        """Redirect anonymous requests to login instead of returning a 403."""
        company = Company.objects.create(
            SrcKey="",
            Name="Company",
            Address="",
            Country="USA",
            Status=Status.objects.create(status="Active"),
            Industry=Industry.objects.create(industry="Hemp"),
            Grower=Grower.objects.create(grower="Grower"),
        )
        change = self._pending_change()
        paths = (
            reverse("companies"),
            reverse("company-view", args=[company.pk]),
            reverse("company-filtered"),
            reverse("export-companies"),
            reverse("changes"),
            reverse("my_changes"),
            reverse("company-view-pending", args=[change.pk]),
            reverse("upload-wizard"),
            reverse("upload"),
            reverse("categories"),
            reverse("export-categories"),
        )

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/user/login", response.url)

    def test_authenticated_users_can_view_and_export_every_database(self):
        """Allow signed-in users to read reference tables without application grants."""
        company = Company.objects.create(
            SrcKey="",
            Name="Company",
            Address="",
            Country="USA",
            Status=Status.objects.create(status="Active"),
            Industry=Industry.objects.create(industry="Hemp"),
            Grower=Grower.objects.create(grower="Grower"),
        )
        self.client.force_login(self.unprivileged)

        for path in (
            reverse("companies"),
            reverse("company-view", args=[company.pk]),
            reverse("company-filtered"),
            reverse("export-companies"),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

        for view_name, export_name, _delete_path, _model, _data in self.reference_tables:
            with self.subTest(view=view_name):
                self.assertEqual(self.client.get(reverse(view_name)).status_code, 200)
                self.assertEqual(self.client.get(reverse(export_name)).status_code, 200)

        home = self.client.get(reverse("index"))
        self.assertContains(home, "Databases")

    def test_permission_combinations_control_navigation_and_actions(self):
        """Show each workflow only to users who can perform it."""
        change = self._pending_change()
        expectations = (
            (self.unprivileged, False, False, False, False, False),
            (self.editor, False, True, True, True, False),
            (self.reviewer, True, True, False, False, True),
            (self.metadata_editor, False, False, False, False, False),
            (self.edit_reviewer, True, True, True, True, True),
            (self.edit_metadata_editor, False, False, True, True, False),
            (self.review_metadata_editor, True, True, False, False, True),
            (self.combined, True, True, True, True, True),
            (self.staff, False, False, False, False, False),
            (self.superuser, True, True, True, True, True),
        )

        for (
            user,
            changes,
            pending_access,
            uploads,
            company_actions,
            review_actions,
        ) in expectations:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                home = self.client.get(reverse("index"))
                companies = self.client.get(reverse("companies"))
                pending = self.client.get(
                    reverse("company-view-pending", args=[change.pk])
                )

                self.assertEqual('href="/changes"' in home.content.decode(), changes)
                self.assertEqual('href="/upload_wizard"' in home.content.decode(), uploads)
                self.assertEqual(
                    'data-bs-target="#createModal"' in companies.content.decode(),
                    company_actions,
                )
                self.assertEqual(
                    'data-bs-target="#importModal"' in companies.content.decode(),
                    company_actions,
                )
                if pending_access:
                    self.assertEqual(pending.status_code, 200)
                    self.assertEqual("Approve" in pending.content.decode(), review_actions)
                    self.assertEqual("Reject" in pending.content.decode(), review_actions)
                else:
                    self.assertEqual(pending.status_code, 403)

    def test_company_change_permissions_are_independent(self):
        """Keep submission, review, and upload access separate."""
        change = self._pending_change()
        pending_url = reverse("company-view-pending", args=[change.pk])

        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("my_changes")).status_code, 200)
        self.assertEqual(self.client.get(pending_url).status_code, 200)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("upload")).status_code, 405)
        self.assertEqual(
            self.client.post(reverse("company-pending-approve", args=[change.pk])).status_code,
            403,
        )

        other_change = self._pending_change(
            author=self.edit_metadata_editor,
            name="Another editor's pending company",
        )
        self.assertEqual(
            self.client.get(
                reverse("company-view-pending", args=[other_change.pk])
            ).status_code,
            403,
        )

        self.client.force_login(self.reviewer)
        response = self.client.get(pending_url)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approve")
        self.assertContains(response, "Reject")
        self.assertEqual(self.client.get(reverse("my_changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload")).status_code, 403)

        self.client.force_login(self.unprivileged)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)
        self.assertEqual(self.client.get(pending_url).status_code, 403)
        self.assertEqual(self.client.get(reverse("my_changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 403)

    @patch("helloworld.views.email_admins")
    @patch("helloworld.views.geocode_location", return_value=(None, None))
    def test_only_edit_companies_can_submit_company_changes(self, _geocode, _email_admins):
        """Require the edit permission for direct company submissions."""
        submission = self._company_submission()

        self.client.force_login(self.unprivileged)
        denied = self.client.post(reverse("companies"), submission)
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(PendingChanges.objects.exists())

        self.client.force_login(self.editor)
        response = self.client.post(reverse("companies"), submission)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            PendingChanges.objects.get(author=self.editor).pending_company.Name,
            "Submitted company",
        )

    def test_my_changes_shows_only_the_current_editors_submissions(self):
        """Keep My Changes scoped to the signed-in editor."""
        self._pending_change(author=self.editor, name="Editor proposal")
        self._pending_change(author=self.combined, name="Other proposal")
        self.client.force_login(self.editor)

        response = self.client.get(reverse("my_changes"))

        self.assertContains(response, "Editor proposal")
        self.assertNotContains(response, "Other proposal")

    @patch("helloworld.views.email_admins")
    def test_company_edits_and_deletion_requests_require_edit_companies(
        self, _email_admins
    ):
        """Allow editors to request changes while every other user is denied."""
        company = Company.objects.create(
            SrcKey="", Name="Protected company", Address="", Country="USA"
        )
        edit_url = reverse("edit-company", args=[company.pk])
        delete_url = reverse("remove-company", args=[company.pk])
        for user in (
            self.unprivileged,
            self.reviewer,
            self.metadata_editor,
            self.review_metadata_editor,
            self.staff,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.post(edit_url, {"Name": "Unauthorized"}).status_code,
                    403,
                )
                self.assertEqual(self.client.post(delete_url).status_code, 403)
                company.refresh_from_db()
                self.assertEqual(company.Name, "Protected company")
                self.assertFalse(
                    PendingChanges.objects.filter(company=company).exists()
                )

        self.client.force_login(self.editor)
        self.assertEqual(self.client.post(delete_url).status_code, 302)
        self.assertTrue(Company.objects.filter(pk=company.pk).exists())
        self.assertTrue(
            PendingChanges.objects.filter(
                company=company, author=self.editor, changeType="deletion"
            ).exists()
        )

    def test_reviewers_can_approve_and_reject_but_editors_cannot(self):
        """Require review permission for both pending-change decisions."""
        approve_change = self._pending_change(name="Approve me")
        reject_change = self._pending_change(name="Reject me")

        self.client.force_login(self.editor)
        self.assertEqual(
            self.client.post(reverse("company-pending-approve", args=[approve_change.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("company-pending-reject", args=[reject_change.pk])).status_code,
            403,
        )

        self.client.force_login(self.reviewer)
        approved = self.client.post(reverse("company-pending-approve", args=[approve_change.pk]))
        rejected = self.client.post(reverse("company-pending-reject", args=[reject_change.pk]))
        self.assertEqual(approved.status_code, 302)
        self.assertEqual(rejected.status_code, 302)
        approve_change.refresh_from_db()
        reject_change.refresh_from_db()
        self.assertEqual(approve_change.status, PendingChanges.PendingStatus.APPROVED)
        self.assertEqual(reject_change.status, PendingChanges.PendingStatus.REJECTED)

    def test_upload_workflow_keeps_post_and_csrf_protection(self):
        """Allow editors to stage and cancel uploads through CSRF-protected posts."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        self.assertEqual(client.get(reverse("companies")).status_code, 200)
        csrf_token = client.cookies["csrftoken"].value
        staged = client.post(
            reverse("upload"),
            {"file": self._upload_file(), "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(staged.status_code, 302)
        self.assertTrue(PendingCompany.objects.filter(Name="Staged company").exists())
        self.assertTrue(UploadIndex.objects.exists())

        self.assertEqual(client.post(reverse("upload-wizard"), {"cancel": "1"}).status_code, 403)
        client.get(reverse("upload-wizard"))
        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("upload-wizard"),
            {"cancel": "1", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PendingCompany.objects.filter(Name="Staged company").exists())
        self.assertFalse(UploadIndex.objects.exists())

    def test_reviewers_cannot_post_upload_actions(self):
        """Keep review-only users out of every upload mutation endpoint."""
        self.client.force_login(self.reviewer)
        for data in ({"add-all": "1"}, {"add-unique": "1"}, {"cancel": "1"}):
            with self.subTest(data=data):
                self.assertEqual(
                    self.client.post(reverse("upload-wizard"), data).status_code,
                    403,
                )
        self.assertEqual(self.client.post(reverse("upload"), {}).status_code, 403)

    def test_editor_can_finish_a_staged_upload(self):
        """Allow an editor to promote staged uploads into companies."""
        staged = PendingCompany.objects.create(
            SrcKey="", Name="Finished upload", Address="", Country="USA"
        )
        UploadIndex.objects.create(pendingID=str(staged.pk))
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        client.get(reverse("upload-wizard"))
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("upload-wizard"),
            {"add-all": "1", "csrfmiddlewaretoken": csrf_token},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Company.objects.filter(Name="Finished upload").exists())
        self.assertFalse(UploadIndex.objects.exists())

    def test_approval_and_metadata_writes_require_csrf(self):
        """Retain CSRF checks for approval and reference-table mutations."""
        change = self._pending_change()
        reviewer_client = Client(enforce_csrf_checks=True)
        reviewer_client.force_login(self.reviewer)
        pending_url = reverse("company-view-pending", args=[change.pk])
        reviewer_client.get(pending_url)
        csrf_token = reviewer_client.cookies["csrftoken"].value
        approve_url = reverse("company-pending-approve", args=[change.pk])
        self.assertEqual(reviewer_client.post(approve_url).status_code, 403)
        self.assertEqual(
            reviewer_client.post(approve_url, {"csrfmiddlewaretoken": csrf_token}).status_code,
            302,
        )

        metadata_client = Client(enforce_csrf_checks=True)
        metadata_client.force_login(self.metadata_editor)
        metadata_client.get(reverse("categories"))
        csrf_token = metadata_client.cookies["csrftoken"].value
        self.assertEqual(
            metadata_client.post(
                reverse("categories"),
                {"category": "CSRF category", "csrfmiddlewaretoken": csrf_token},
            ).status_code,
            302,
        )
        category = Category.objects.get(category="CSRF category")
        delete_url = f"/remove_categories/{category.pk}"
        self.assertEqual(metadata_client.post(delete_url).status_code, 403)
        self.assertEqual(
            metadata_client.post(delete_url, {"csrfmiddlewaretoken": csrf_token}).status_code,
            302,
        )

    def test_edit_metadata_controls_every_reference_table(self):
        """Limit existing reference-table creates and deletes to metadata editors."""
        self.client.force_login(self.unprivileged)
        for view_name, _export_name, delete_path, model, data in self.reference_tables:
            with self.subTest(view=view_name, user="unprivileged"):
                response = self.client.post(reverse(view_name), data)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(model.objects.exists())
                page = self.client.get(reverse(view_name))
                self.assertNotContains(page, f"/{delete_path}/")

        self.client.force_login(self.metadata_editor)
        for view_name, _export_name, delete_path, model, data in self.reference_tables:
            with self.subTest(view=view_name, user="metadata_editor"):
                response = self.client.post(
                    reverse(view_name), self._reference_data(model, data)
                )
                self.assertEqual(response.status_code, 302)
                record = model.objects.get()
                page = self.client.get(reverse(view_name))
                self.assertContains(page, f"/{delete_path}/{record.pk}")
                self.assertEqual(self.client.get(f"/{delete_path}/{record.pk}").status_code, 405)
                deleted = self.client.post(f"/{delete_path}/{record.pk}")
                self.assertEqual(deleted.status_code, 302)
                self.assertFalse(model.objects.exists())

    def test_staff_and_superuser_keep_their_distinct_access(self):
        """Keep Staff from gaining application access while superusers retain it."""
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 403)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("categories")).status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_legacy_feature_permissions_do_not_authorize_new_workflows(self):
        """Leave historical permissions unable to open replacement features."""
        old_permissions = (
            self._legacy_permission(codename)
            for codename in (
                "submit_company_change",
                "review_pending_change",
                "upload_company_data",
                "review_company_upload",
            )
        )
        self.legacy.user_permissions.add(*old_permissions)
        self.client.force_login(self.legacy)

        self.assertEqual(self.client.get(reverse("changes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("upload-wizard")).status_code, 403)
        self.assertEqual(self.client.post(reverse("companies"), self._company_submission()).status_code, 403)

    def test_explicit_group_permission_authorizes_without_role_names(self):
        """Respect Django's explicit group permission assignment."""
        group = Group.objects.create(name="Any name")
        permission = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Company),
            codename=REVIEW_COMPANY_CHANGES.rsplit(".", 1)[1],
        )
        group.permissions.add(permission)
        self.unprivileged.groups.add(group)
        self.client.force_login(self.unprivileged)

        self.assertEqual(self.client.get(reverse("changes")).status_code, 200)

    @patch("helloworld.notifications.send_mail")
    @patch("helloworld.notifications.settings.DEBUG", True)
    def test_approval_notifications_reach_only_reviewers(self, send_mail):
        """Notify active users with the review permission and superusers."""
        self.reviewer.email = "reviewer@example.test"
        self.reviewer.save(update_fields=["email"])
        self.editor.email = "editor@example.test"
        self.editor.save(update_fields=["email"])
        self.legacy.email = "legacy@example.test"
        self.legacy.save(update_fields=["email"])
        self.superuser.email = "superuser@example.test"
        self.superuser.save(update_fields=["email"])
        self.legacy.user_permissions.add(
            self._legacy_permission("review_pending_change")
        )

        email_admins("created", "Pending company", 1, "testserver")

        recipients = set(send_mail.call_args.kwargs["recipient_list"])
        self.assertEqual(recipients, {"reviewer@example.test", "superuser@example.test"})
        self.assertEqual(
            set(
                users_with_application_permission(REVIEW_COMPANY_CHANGES)
                .values_list("pk", flat=True)
            ),
            {
                self.reviewer.pk,
                self.edit_reviewer.pk,
                self.review_metadata_editor.pk,
                self.superuser.pk,
                self.combined.pk,
            },
        )


class PermissionMigrationTests(TransactionTestCase):
    """Check that the permission migration does not grant access."""

    migrate_from = [("helloworld", "0018_pendingcompany_import_batch_id")]
    migrate_to = [("helloworld", "0019_feature_permissions")]

    def setUp(self):
        """Move the test database to the state before feature permissions."""
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)

    def tearDown(self):
        """Restore the database for tests that follow this migration check."""
        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        super().tearDown()

    def test_upgrade_keeps_historical_grants_without_new_grants(self):
        """Require administrators to assign feature permissions after upgrading."""
        User = get_user_model()
        direct_user = User.objects.create(username="legacy-direct", is_active=True)
        grouped_user = User.objects.create(username="legacy-grouped", is_active=True)
        group = Group.objects.create(name="legacy-group")
        grouped_user.groups.add(group)

        pending_change_type = ContentType.objects.get_for_model(PendingChanges)
        pending_company_type = ContentType.objects.get_for_model(PendingCompany)
        old_direct = Permission.objects.get_or_create(
            content_type=pending_change_type,
            codename="submit_company_change",
            defaults={"name": "Can submit company changes"},
        )[0]
        old_group = Permission.objects.get_or_create(
            content_type=pending_company_type,
            codename="review_company_upload",
            defaults={"name": "Can review a company upload"},
        )[0]
        direct_user.user_permissions.add(old_direct)
        group.permissions.add(old_group)

        Permission.objects.filter(
            content_type__app_label="helloworld",
            codename__in=("edit_companies", "review_company_changes", "edit_metadata"),
        ).delete()

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        create_permissions(
            apps.get_app_config("helloworld"),
            verbosity=0,
            interactive=False,
            using=connection.alias,
        )

        direct_user = get_user_model().objects.get(pk=direct_user.pk)
        grouped_user = get_user_model().objects.get(pk=grouped_user.pk)
        group.refresh_from_db()
        self.assertTrue(direct_user.user_permissions.filter(pk=old_direct.pk).exists())
        self.assertTrue(group.permissions.filter(pk=old_group.pk).exists())
        for codename in ("edit_companies", "review_company_changes", "edit_metadata"):
            permission = Permission.objects.get(codename=codename, content_type__app_label="helloworld")
            with self.subTest(permission=codename):
                self.assertFalse(permission.user_set.filter(pk=direct_user.pk).exists())
                self.assertFalse(permission.group_set.filter(pk=group.pk).exists())
                self.assertFalse(direct_user.has_perm(f"helloworld.{codename}"))
                self.assertFalse(grouped_user.has_perm(f"helloworld.{codename}"))
