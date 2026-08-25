from django.contrib.auth.models import Permission, User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from . import views
from .models import (
    Category,
    Company,
    Grower,
    Industry,
    PendingChanges,
    PendingCompany,
    ProductGroup,
    Resources,
    Solution,
    Stage,
    Status,
    stakeholderGroups,
)


class AuditSecurityTests(TestCase):
    """Regression tests for mutation methods and model add permissions."""

    def setUp(self):
        """Create a staff user and authenticate the default test client."""
        self.staff = User.objects.create_user(
            username="staff",
            password="password",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def grant_permission(self, user, codename):
        """Grant a helloworld model permission to a test user."""
        permission = Permission.objects.get(
            content_type__app_label="helloworld",
            codename=codename,
        )
        user.user_permissions.add(permission)

    def create_company(self):
        """Create the minimum company record needed by mutation tests."""
        return Company.objects.create(
            SrcKey="", Name="Example", Address="", Country="US"
        )

    def create_pending_change(self, change_type="create"):
        """Create a pending company change for approval tests."""
        pending_company = PendingCompany.objects.create(
            SrcKey="", Name="Example", Address="", Country="US"
        )
        return PendingChanges.objects.create(
            pending_company=pending_company,
            changeType=change_type,
            author=self.staff,
        )

    def test_company_delete_get_is_405_and_does_not_create_change(self):
        """A GET cannot submit a company deletion proposal."""
        company = self.create_company()

        response = self.client.get(reverse("remove-company", args=[company.id]))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(PendingChanges.objects.exists())

    def test_company_delete_post_creates_pending_change(self):
        """A staff POST can submit a company deletion proposal."""
        company = self.create_company()

        response = self.client.post(reverse("remove-company", args=[company.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/companies")
        self.assertTrue(
            PendingChanges.objects.filter(company=company, changeType="deletion").exists()
        )

    def test_pending_change_gets_are_405_and_do_not_mutate(self):
        """GET cannot approve or reject a pending company change."""
        for endpoint in ("company-pending-approve", "company-pending-reject"):
            with self.subTest(endpoint=endpoint):
                change = self.create_pending_change()
                response = self.client.get(reverse(endpoint, args=[change.id]))

                change.refresh_from_db()
                self.assertEqual(response.status_code, 405)
                self.assertEqual(change.status, PendingChanges.PendingStatus.PENDING)

    def lookup_delete_cases(self):
        """Return lookup models, deletion paths, and redirect targets."""
        return (
            (Category, "remove_categories", "/categories", {"category": "Example"}),
            (Solution, "remove_solutions", "/solutions", {"solution": "Example"}),
            (
                stakeholderGroups,
                "remove_stakeholder_groups",
                "/stakeholder-groups",
                {"stakeholderGroup": "Example", "category": 1},
            ),
            (Stage, "remove_stages", "/stages", {"stage": "Example"}),
            (
                ProductGroup,
                "remove_product_group",
                "/product-groups",
                {"productGroup": "Example"},
            ),
            (Status, "remove_status", "/status", {"status": "Example"}),
            (Grower, "remove_grower", "/grower", {"grower": "Example"}),
            (Industry, "remove_industry", "/industry", {"industry": "Example"}),
        )

    def test_all_lookup_delete_gets_are_405_and_do_not_delete(self):
        """GET cannot delete any in-scope lookup record."""
        for model, endpoint, _redirect, fields in self.lookup_delete_cases():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)
                response = self.client.get(f"/{endpoint}/{record.id}")

                self.assertEqual(response.status_code, 405)
                self.assertTrue(model.objects.filter(pk=record.pk).exists())

    def test_all_lookup_delete_posts_delete_records(self):
        """Staff POSTs can delete each in-scope lookup record."""
        for model, endpoint, redirect_target, fields in self.lookup_delete_cases():
            with self.subTest(model=model.__name__):
                record = model.objects.create(**fields)
                response = self.client.post(f"/{endpoint}/{record.id}")

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], redirect_target)
                self.assertFalse(model.objects.filter(pk=record.pk).exists())

    def test_csrf_is_required_for_company_delete_post(self):
        """Mutation forms must pass Django's CSRF validation."""
        company = self.create_company()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)

        response = csrf_client.post(reverse("remove-company", args=[company.id]))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PendingChanges.objects.exists())

    def test_view_only_user_cannot_create_category(self):
        """A view-only user cannot submit a lookup creation POST."""
        user = User.objects.create_user(username="viewer", password="password")
        self.grant_permission(user, "view_category")
        self.client.force_login(user)

        response = self.client.post("/categories/", {"category": "Forbidden"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Category.objects.filter(category="Forbidden").exists())

    def test_view_only_user_cannot_propose_pending_company(self):
        """A view-only user cannot submit a pending company proposal."""
        user = User.objects.create_user(username="company-viewer", password="password")
        self.grant_permission(user, "view_company")
        self.client.force_login(user)

        response = self.client.post(
            "/companies/",
            {
                "SrcKey": "",
                "Name": "Forbidden",
                "Address": "",
                "Country": "US",
                "Latitude": "1",
                "Longitude": "1",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PendingCompany.objects.filter(Name="Forbidden").exists())

    def test_add_user_can_create_category(self):
        """A user with add permission can submit a lookup creation POST."""
        user = User.objects.create_user(username="creator", password="password")
        self.grant_permission(user, "add_category")
        self.client.force_login(user)

        response = self.client.post("/categories/", {"category": "Allowed"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/categories")
        self.assertTrue(Category.objects.filter(category="Allowed").exists())

    def test_add_user_can_propose_pending_company(self):
        """A user with add permission can submit a pending company proposal."""
        user = User.objects.create_user(username="company-creator", password="password")
        self.grant_permission(user, "add_pendingcompany")
        self.client.force_login(user)
        industry = Industry.objects.create(industry="Example")
        status = Status.objects.create(status="Example")
        grower = Grower.objects.create(grower="Example")

        response = self.client.post(
            "/companies/",
            {
                "SrcKey": "",
                "Name": "Allowed",
                "Address": "",
                "Industry": industry.id,
                "Status": status.id,
                "Grower": grower.id,
                "Country": "US",
                "Latitude": "1",
                "Longitude": "1",
                "dateCreated": "2026-01-01 00:00:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/companies")
        self.assertTrue(PendingCompany.objects.filter(Name="Allowed").exists())

    def test_pending_approval_post_approves_change(self):
        """A staff POST approves a pending company change."""
        change = self.create_pending_change()

        response = self.client.post(
            reverse("company-pending-approve", args=[change.id])
        )

        change.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/changes")
        self.assertEqual(change.status, PendingChanges.PendingStatus.APPROVED)
        self.assertTrue(Company.objects.filter(Name="Example").exists())

    def test_pending_rejection_post_rejects_change(self):
        """A staff POST rejects a pending company change."""
        change = self.create_pending_change()

        response = self.client.post(
            reverse("company-pending-reject", args=[change.id])
        )

        change.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/changes")
        self.assertEqual(change.status, PendingChanges.PendingStatus.REJECTED)

    def test_resource_delete_get_is_405_and_does_not_delete(self):
        """The unregistered resource deletion view rejects GET without mutation."""
        resource = Resources.objects.create(type="about")
        request = RequestFactory().get(f"/remove_resource/{resource.id}")
        request.user = self.staff

        response = views.remove_resource(request, resource.id)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Resources.objects.filter(pk=resource.pk).exists())
