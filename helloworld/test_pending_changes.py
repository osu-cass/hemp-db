"""Tests for progressively loaded pending changes."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import Company, PendingChanges, PendingCompany
from .pending_changes import (
    get_category_counts,
    get_change_page,
    get_company_page,
)
from .permissions import EDIT_COMPANIES, REVIEW_COMPANY_CHANGES
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
        cls.reviewer = get_user_model().objects.create_user(
            username="reviewer",
            password="test-password",
        )
        cls.reviewer.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Company),
                codename=REVIEW_COMPANY_CHANGES.rsplit(".", 1)[1],
            )
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

    def test_company_pages_order_newest_change_first_in_every_category(self):
        """Sort by newest pending change, breaking ties by higher company ID."""
        older = self.create_company("Older edit")
        newer = self.create_company("Newer edit")
        older_change = self.create_change("edit", company=older)
        self.create_change("edit", company=older)
        newer_change = self.create_change("edit", company=newer)
        base_time = timezone.now()
        PendingChanges.objects.filter(company=older).update(
            created_at=base_time - timedelta(minutes=2)
        )
        PendingChanges.objects.filter(id=older_change.id).update(
            created_at=base_time - timedelta(minutes=3)
        )
        PendingChanges.objects.filter(id=newer_change.id).update(created_at=base_time)

        with self.assertNumQueries(1):
            edit_page = get_company_page("edit", page_size=1)
        with self.assertNumQueries(1):
            next_edit_page = get_company_page(
                "edit", edit_page.next_cursor, page_size=1
            )

        self.assertEqual(edit_page.items[0].company_id, newer.id)
        self.assertEqual(next_edit_page.items[0].company_id, older.id)
        self.assertEqual(next_edit_page.items[0].pending_count, 2)
        self.assertIsNone(next_edit_page.next_cursor)

        first_create = self.create_pending_company("First create")
        second_create = self.create_pending_company("Second create")
        newest_create = self.create_pending_company("Newest create")
        self.create_change("create", pending_company=first_create)
        self.create_change("create", pending_company=second_create)
        newest_change = self.create_change("create", pending_company=newest_create)
        tied_time = timezone.now() + timedelta(minutes=1)
        PendingChanges.objects.filter(
            pending_company__in=[first_create, second_create]
        ).update(created_at=tied_time)
        PendingChanges.objects.filter(id=newest_change.id).update(
            created_at=tied_time + timedelta(minutes=1)
        )

        create_page = get_company_page("create", page_size=2)
        next_create_page = get_company_page(
            "create", create_page.next_cursor, page_size=2
        )

        self.assertEqual(
            [item.company_id for item in create_page.items],
            [newest_create.id, second_create.id],
        )
        self.assertEqual(
            [item.company_id for item in next_create_page.items],
            [first_create.id],
        )

    def test_company_page_cursor_survives_review_between_pages(self):
        """Skip companies reviewed after the previous page was loaded."""
        first_delete = self.create_company("First delete")
        second_delete = self.create_company("Second delete")
        first_deletion = self.create_change("deletion", company=first_delete)
        self.create_change("deletion", company=second_delete)
        PendingChanges.objects.filter(id=first_deletion.id).update(
            created_at=timezone.now() - timedelta(minutes=1)
        )

        delete_page = get_company_page("delete", page_size=1)
        first_deletion.status = PendingChanges.PendingStatus.APPROVED
        first_deletion.save(update_fields=["status"])
        next_delete_page = get_company_page(
            "delete", delete_page.next_cursor, page_size=1
        )

        self.assertEqual(delete_page.items[0].company_id, second_delete.id)
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

    def test_malformed_cursors_raise_value_error(self):
        """Reject cursors without an aware timestamp and numeric ID."""
        for cursor in ("invalid", "2026-01-01T00:00:00_1", "2026-01-01T00:00:00+00:00_x"):
            with self.subTest(cursor=cursor), self.assertRaises(ValueError):
                get_company_page("edit", cursor)


class PendingChangeFragmentTests(PendingChangesTestBase):
    """Verify fragment limits, permissions, and query bounds."""

    def setUp(self):
        """Create a request factory for query-count assertions."""
        self.factory = RequestFactory()

    def reviewer_request(self, path: str):
        """Build a GET request from the reviewer."""
        request = self.factory.get(path)
        request.user = self.reviewer
        # Warm the permission cache so query counts cover only the view.
        request.user.get_all_permissions()
        return request

    def test_initial_page_contains_counts_but_no_company_or_change_rows(self):
        """Keep the initial response to the shell and category counts."""
        company = self.create_company("Initial edit")
        self.create_change("edit", company=company)
        request = self.reviewer_request("/changes/")

        # Category counts and upload batches.
        with self.assertNumQueries(2):
            response = dbChanges(request)

        self.assertContains(response, "Edit Changes (1)")
        self.assertNotContains(response, "Initial edit")
        self.assertNotContains(response, "data-pending-key")

    def test_fragment_endpoints_require_permission_and_get(self):
        """Redirect anonymous users, deny unprivileged ones, and allow only GET."""
        companies_url = reverse("pending-change-companies", args=["edit"])
        changes_url = reverse(
            "pending-company-changes", args=["edit", 1]
        )

        self.assertEqual(self.client.get(companies_url).status_code, 302)
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(changes_url).status_code, 403)
        self.client.force_login(self.reviewer)
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
        request = self.reviewer_request(
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
        request = self.reviewer_request(
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
        unknown_request = self.reviewer_request("/changes/unknown/companies/")
        invalid_cursor_request = self.reviewer_request(
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


class MyChangesQueryTests(PendingChangesTestBase):
    """Verify the author's change list does not query per row."""

    def test_query_count_does_not_grow_with_changes(self):
        """Load company names in the list query."""
        self.author.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Company),
                codename=EDIT_COMPANIES.rsplit(".", 1)[1],
            )
        )
        self.client.force_login(self.author)

        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse("my_changes"))
            self.assertEqual(response.status_code, 200)
            return len(queries)

        self.create_change("edit", company=self.create_company("Edit 1"))
        self.create_change("create", pending_company=self.create_pending_company("New 1"))
        baseline = count_queries()
        for index in range(2, 5):
            self.create_change("edit", company=self.create_company(f"Edit {index}"))
            self.create_change(
                "create", pending_company=self.create_pending_company(f"New {index}")
            )

        self.assertEqual(count_queries(), baseline)
