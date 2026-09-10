"""Tests for progressively loaded pending changes."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Company, PendingChanges, PendingCompany
from .pending_changes import (
    InvalidCursor,
    get_category_counts,
    get_change_page,
    get_company_page,
)
from .views import dbChanges, pending_change_companies, pending_company_changes


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class PendingChangesTestBase(TestCase):
    """Provide pending-change records with minimal company data."""

    @classmethod
    def setUpTestData(cls):
        """Create users shared by pending-change tests."""
        cls.staff_user = get_user_model().objects.create_user(
            username="reviewer",
            password="test-password",
            is_staff=True,
        )
        cls.regular_user = get_user_model().objects.create_user(
            username="reader",
            password="test-password",
        )
        cls.author = get_user_model().objects.create_user(username="author")

    def create_company(self, name: str) -> Company:
        """Create a company with only its required text fields."""
        return Company.objects.create(
            SrcKey=f"company-{name}",
            Name=name,
            Address="",
            Country="USA",
        )

    def create_pending_company(self, name: str) -> PendingCompany:
        """Create a pending company with only its required text fields."""
        return PendingCompany.objects.create(
            SrcKey=f"pending-{name}",
            Name=name,
            Address="",
            Country="USA",
        )

    def create_change(
        self,
        change_type: str,
        *,
        company: Company | None = None,
        pending_company: PendingCompany | None = None,
        status: str = PendingChanges.PendingStatus.PENDING,
        author=None,
    ) -> PendingChanges:
        """Create a pending change for a company or pending company."""
        return PendingChanges.objects.create(
            changeType=change_type,
            company=company,
            pending_company=pending_company,
            status=status,
            author=self.author if author is None else author,
        )


class PendingChangeQueryTests(PendingChangesTestBase):
    """Verify grouped counts and keyset pages."""

    def test_counts_group_companies_and_include_only_pending_changes(self):
        """Count each company once and exclude reviewed rows."""
        company = self.create_company("Edited")
        deleted = self.create_company("Deleted")
        pending = self.create_pending_company("Created")
        reviewed = self.create_pending_company("Reviewed")

        self.create_change("edit", company=company)
        self.create_change("edit", company=company)
        self.create_change("deletion", company=deleted)
        self.create_change("create", pending_company=pending)
        self.create_change("create", pending_company=pending)
        self.create_change(
            "create",
            pending_company=reviewed,
            status=PendingChanges.PendingStatus.APPROVED,
        )

        with self.assertNumQueries(1):
            counts = get_category_counts()

        self.assertEqual(counts, {"edit": 1, "create": 1, "delete": 1})

    def test_company_pages_group_and_follow_category_ordering(self):
        """Use company IDs for edits and newest timestamps for creates."""
        first = self.create_company("First edit")
        second = self.create_company("Second edit")
        self.create_change("edit", company=second)
        self.create_change("edit", company=first)
        self.create_change("edit", company=first)

        with self.assertNumQueries(1):
            edit_page = get_company_page("edit", page_size=1)
        with self.assertNumQueries(1):
            next_edit_page = get_company_page(
                "edit", edit_page.next_cursor, page_size=1
            )

        self.assertEqual(edit_page.items[0].company_id, first.id)
        self.assertEqual(edit_page.items[0].pending_count, 2)
        self.assertEqual(next_edit_page.items[0].company_id, second.id)

        first_create = self.create_pending_company("First create")
        second_create = self.create_pending_company("Second create")
        newest_create = self.create_pending_company("Newest create")
        first_change = self.create_change(
            "create", pending_company=first_create
        )
        second_change = self.create_change(
            "create", pending_company=second_create
        )
        newest_change = self.create_change(
            "create", pending_company=newest_create
        )
        tied_time = timezone.now() + timedelta(minutes=1)
        PendingChanges.objects.filter(id__in=[first_change.id, second_change.id]).update(
            created_at=tied_time
        )
        PendingChanges.objects.filter(id=newest_change.id).update(
            created_at=tied_time + timedelta(minutes=1)
        )

        create_page = get_company_page("create", page_size=2)
        next_create_page = get_company_page(
            "create", create_page.next_cursor, page_size=2
        )

        self.assertEqual(create_page.items[0].company_id, newest_create.id)
        self.assertEqual(create_page.items[1].company_id, first_create.id)
        self.assertEqual(next_create_page.items[0].company_id, second_create.id)

        first_delete = self.create_company("First delete")
        second_delete = self.create_company("Second delete")
        self.create_change("deletion", company=first_delete)
        second_deletion = self.create_change("deletion", company=second_delete)
        delete_page = get_company_page("delete", page_size=1)
        second_deletion.status = PendingChanges.PendingStatus.APPROVED
        second_deletion.save(update_fields=["status"])
        next_delete_page = get_company_page(
            "delete", delete_page.next_cursor, page_size=1
        )

        self.assertEqual(delete_page.items[0].company_id, first_delete.id)
        self.assertEqual(next_delete_page.items, [])

    def test_change_pages_are_pending_only_and_survive_review_between_pages(self):
        """Keep cursor boundaries valid when an unseen row is reviewed."""
        company = self.create_company("Many edits")
        oldest = self.create_change("edit", company=company)
        reviewed = self.create_change("edit", company=company)
        newest = self.create_change("edit", company=company)
        base_time = timezone.now()
        PendingChanges.objects.filter(id=oldest.id).update(
            created_at=base_time - timedelta(minutes=2)
        )
        PendingChanges.objects.filter(id=reviewed.id).update(
            created_at=base_time
        )
        PendingChanges.objects.filter(id=newest.id).update(created_at=base_time)

        with self.assertNumQueries(1):
            page = get_change_page("edit", company.id, page_size=1)
            self.assertEqual(page.items[0].author.username, self.author.username)
        PendingChanges.objects.filter(id=reviewed.id).update(
            status=PendingChanges.PendingStatus.APPROVED
        )
        with self.assertNumQueries(1):
            next_page = get_change_page(
                "edit", company.id, page.next_cursor, page_size=1
            )

        self.assertEqual([change.id for change in page.items], [newest.id])
        self.assertEqual([change.id for change in next_page.items], [oldest.id])
        self.assertIsNone(next_page.next_cursor)

    def test_cursor_cannot_be_reused_for_another_result_set(self):
        """Reject a cursor for another category."""
        company = self.create_company("Cursor company")
        another_company = self.create_company("Another company")
        self.create_change("edit", company=company)
        self.create_change("edit", company=another_company)
        page = get_company_page("edit", page_size=1)

        with self.assertRaises(InvalidCursor):
            get_company_page("delete", page.next_cursor, page_size=1)


class PendingChangeFragmentTests(PendingChangesTestBase):
    """Verify fragment limits, permissions, and query bounds."""

    def setUp(self):
        """Create a request factory for query-count assertions."""
        self.factory = RequestFactory()

    def staff_request(self, path: str):
        """Build a GET request from the staff reviewer."""
        request = self.factory.get(path)
        request.user = self.staff_user
        return request

    def test_initial_page_contains_counts_but_no_company_or_change_rows(self):
        """Keep the initial response to the shell and category counts."""
        company = self.create_company("Initial edit")
        self.create_change("edit", company=company)
        request = self.staff_request("/changes/")
        # Warm the permission cache used by master.html.
        self.staff_user.get_all_permissions()

        with self.assertNumQueries(1):
            response = dbChanges(request)

        self.assertContains(response, "Edit Changes (1)")
        self.assertNotContains(response, "Initial edit")
        self.assertNotContains(response, "data-pending-key")

    def test_fragment_endpoints_require_staff_and_get(self):
        """Redirect nonstaff users and reject non-GET staff requests."""
        companies_url = reverse("pending-change-companies", args=["edit"])
        changes_url = reverse(
            "pending-company-changes", args=["edit", 1]
        )

        self.assertEqual(self.client.get(companies_url).status_code, 302)
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(changes_url).status_code, 302)
        self.client.force_login(self.staff_user)
        self.assertEqual(self.client.post(companies_url).status_code, 405)
        self.assertEqual(self.client.post(changes_url).status_code, 405)

    def test_company_fragment_is_one_query_and_limited_to_100_summaries(self):
        """Bound company summaries without adding per-company queries."""
        Company.objects.bulk_create(
            [
                Company(
                    SrcKey=f"bulk-{index}",
                    Name=f"Company {index:03}",
                    Address="",
                    Country="USA",
                )
                for index in range(101)
            ]
        )
        companies = list(Company.objects.order_by("id"))
        PendingChanges.objects.bulk_create(
            [
                PendingChanges(
                    company_id=company.id,
                    author_id=self.author.id,
                    changeType="edit",
                )
                for company in companies
            ]
        )
        request = self.staff_request(
            reverse("pending-change-companies", args=["edit"])
        )

        with self.assertNumQueries(1):
            response = pending_change_companies(request, "edit")

        self.assertEqual(response.content.count(b"data-pending-key="), 100)
        self.assertContains(response, "?cursor=")

    def test_change_fragment_is_one_query_limited_and_handles_missing_author(self):
        """Fetch authors in the row query and render deleted authors safely."""
        company = self.create_company("Large history")
        PendingChanges.objects.bulk_create(
            [
                PendingChanges(
                    company=company,
                    pending_company=None,
                    author=self.author,
                    changeType="edit",
                )
                for _ in range(100)
            ]
            + [
                PendingChanges(
                    company=company,
                    pending_company=None,
                    author=None,
                    changeType="edit",
                    created_at=timezone.now() + timedelta(minutes=1),
                )
            ]
        )
        request = self.staff_request(
            reverse("pending-company-changes", args=["edit", company.id])
        )

        with self.assertNumQueries(1):
            response = pending_company_changes(request, "edit", company.id)

        missing_author_change = PendingChanges.objects.get(author__isnull=True)
        self.assertEqual(response.content.count(b"data-pending-key="), 100)
        self.assertContains(response, "Unknown")
        self.assertContains(
            response,
            reverse("company-view-pending", args=[missing_author_change.id]),
        )
        self.assertContains(response, "?cursor=")

    def test_invalid_category_and_cursor_return_bad_request(self):
        """Return HTTP 400 for invalid fragment inputs."""
        unknown_request = self.staff_request("/changes/unknown/companies/")
        invalid_cursor_request = self.staff_request(
            "/changes/edit/companies/?cursor=invalid"
        )

        self.assertEqual(
            pending_change_companies(unknown_request, "unknown").status_code,
            400,
        )
        self.assertEqual(
            pending_change_companies(invalid_cursor_request, "edit").status_code,
            400,
        )
