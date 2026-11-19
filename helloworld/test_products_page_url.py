"""Products page URL validation, review workflow, rendering and upload."""

from io import StringIO
from unittest.mock import patch

import pandas as pd
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Company, PendingChanges, PendingCompany
from .permissions import EDIT_COMPANIES, REVIEW_COMPANY_CHANGES
from .test_support import CompanyWorkflowHelpers
from .test_upload import UploadTestBase
from .upload import (
    UploadValidationError,
    approve_upload_batch,
    import_pending_companies,
    submit_upload_for_review,
)
from .validators import HTTPS_URL_MESSAGE, validate_https_url

VALID_URL = "https://example.com/products"
INVALID_FORM_URLS = ("javascript:alert(1)", "http://example.com", "/relative", "plain text")


class ValidateHttpsUrlTests(SimpleTestCase):
    """Accept only absolute https:// URLs with a valid host."""

    def test_accepts_https_urls(self):
        """Accept a plain https URL and one with port, path and query."""
        for value in (VALID_URL, "https://shop.example.com:8443/a/b?page=2&sort=name"):
            with self.subTest(value=value):
                validate_https_url(value)

    def test_accepts_maximum_length(self):
        """Accept a URL of exactly 2048 characters."""
        value = "https://example.com/" + "a" * 2028
        self.assertEqual(len(value), 2048)
        validate_https_url(value)

    def test_rejects_unsafe_or_incomplete_values(self):
        """Reject other schemes, relative values, bad hosts and control characters."""
        values = (
            "http://example.com",
            "javascript:alert(1)",
            "data:text/html,x",
            "vbscript:msgbox(1)",
            "/relative",
            "example.com/products",
            "plain text",
            "https://",
            "https://exa mple.com",
            "https://example.com/a\tb",
            "https://example.com/a\nb",
            "https://example.com/products\x00",
            "https://example.com/products\x7f",
            "https://example.com/" + "a" * 2029,
        )
        for value in values:
            with self.subTest(value=value):
                with self.assertRaisesMessage(ValidationError, HTTPS_URL_MESSAGE):
                    validate_https_url(value)


class ProductsPageUrlTestBase(CompanyWorkflowHelpers, TestCase):
    """A published company, an editor and a reviewer."""

    def setUp(self):
        """Create the company and both users."""
        self.editor = self._user("editor")
        self.reviewer = self._user("reviewer")
        self._grant(self.editor, EDIT_COMPANIES)
        self._grant(self.reviewer, REVIEW_COMPANY_CHANGES)
        self.submission = self._company_submission()
        self.company = Company.objects.create(
            SrcKey="",
            Name="Published company",
            Address="",
            Country="USA",
            Status_id=self.submission["Status"],
            Industry_id=self.submission["Industry"],
            Grower_id=self.submission["Grower"],
        )
        patcher = patch("helloworld.views.email_admins")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _edit_data(self, url):
        """Return valid edit form data that sets the products page URL."""
        return {
            "SrcKey": self.company.SrcKey,
            "Name": self.company.Name,
            "Address": self.company.Address,
            "Country": self.company.Country,
            "Status": self.company.Status_id,
            "Industry": self.company.Industry_id,
            "Grower": self.company.Grower_id,
            "dateCreated": self.company.dateCreated.isoformat(),
            "ProductsPageUrl": url,
        }

    def _submit_edit(self, url):
        """Submit an edit as the editor and return the pending change."""
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("edit-company", args=[self.company.pk]), self._edit_data(url)
        )
        self.assertRedirects(response, "/companies", fetch_redirect_response=False)
        return PendingChanges.objects.get(company=self.company)

    def _decide(self, change, route):
        """Approve or reject a change as the reviewer."""
        self.client.force_login(self.reviewer)
        response = self.client.post(reverse(route, args=[change.pk]))
        self.assertRedirects(response, "/changes", fetch_redirect_response=False)

    def _published_url(self):
        """Return the company's published products page URL."""
        self.company.refresh_from_db()
        return self.company.ProductsPageUrl

    def _link(self, url):
        """Return the expected products page link markup."""
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
            "View products</a>"
        )


class EditFormTests(ProductsPageUrlTestBase):
    """Edits go through pending review and reject invalid URLs."""

    def test_valid_url_creates_pending_edit_only(self):
        """Stage a valid URL without publishing it."""
        change = self._submit_edit(VALID_URL)

        self.assertEqual(change.changeType, "edit")
        self.assertEqual(change.pending_company.ProductsPageUrl, VALID_URL)
        self.assertEqual(self._published_url(), "")

    def test_invalid_url_rerenders_with_error_and_entered_value(self):
        """Keep the entered value, show the error and stage nothing."""
        self.client.force_login(self.editor)
        for value in INVALID_FORM_URLS:
            with self.subTest(value=value):
                response = self.client.post(
                    reverse("edit-company", args=[self.company.pk]),
                    self._edit_data(value),
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, HTTPS_URL_MESSAGE)
                self.assertContains(response, f'value="{value}"')
                self.assertFalse(PendingCompany.objects.exists())
                self.assertFalse(PendingChanges.objects.exists())

    def test_get_renders_unbound_form(self):
        """Show the current values without validation errors."""
        self.company.ProductsPageUrl = VALID_URL
        self.company.save()
        self.client.force_login(self.editor)

        response = self.client.get(reverse("edit-company", args=[self.company.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_bound)
        self.assertContains(response, f'value="{VALID_URL}"')


class CreateFormTests(ProductsPageUrlTestBase):
    """The create modal rejects invalid URLs without a server error."""

    def test_invalid_url_shows_error_and_creates_nothing(self):
        """Render the page with the error instead of returning a 500."""
        self.client.force_login(self.editor)
        data = {**self.submission, "ProductsPageUrl": "javascript:alert(1)"}

        response = self.client.post(reverse("companies"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Products page URL: {HTTPS_URL_MESSAGE}")
        self.assertFalse(PendingCompany.objects.exists())
        self.assertFalse(PendingChanges.objects.exists())

    @patch("helloworld.views.geocode_location", return_value=(None, None))
    def test_valid_url_is_published_on_approval(self, _geocode):
        """Publish a created company's URL only after approval."""
        self.client.force_login(self.editor)
        data = {**self.submission, "ProductsPageUrl": VALID_URL}

        response = self.client.post(reverse("companies"), data)

        self.assertRedirects(response, "/companies", fetch_redirect_response=False)
        change = PendingChanges.objects.get(changeType="create")
        self.assertFalse(Company.objects.filter(Name=data["Name"]).exists())
        self._decide(change, "company-pending-approve")
        self.assertEqual(Company.objects.get(Name=data["Name"]).ProductsPageUrl, VALID_URL)


class ApprovalWorkflowTests(ProductsPageUrlTestBase):
    """Adding, changing and removing a URL each wait for review."""

    def _start(self, current):
        """Publish the current URL directly."""
        self.company.ProductsPageUrl = current
        self.company.save()

    def _assert_approval_publishes(self, current, proposed):
        """Keep the current value until approval, then publish the proposal."""
        self._start(current)
        change = self._submit_edit(proposed)
        self.assertEqual(self._published_url(), current)

        self._decide(change, "company-pending-approve")

        self.assertEqual(self._published_url(), proposed)

    def _assert_rejection_keeps(self, current, proposed):
        """Leave the current value in place after rejection."""
        self._start(current)
        change = self._submit_edit(proposed)

        self._decide(change, "company-pending-reject")

        self.assertEqual(self._published_url(), current)

    def test_approved_add(self):
        """Publish a new URL on approval."""
        self._assert_approval_publishes("", VALID_URL)

    def test_approved_change(self):
        """Publish a changed URL on approval."""
        self._assert_approval_publishes(VALID_URL, "https://example.com/catalog")

    def test_approved_removal(self):
        """Clear the URL on approval."""
        self._assert_approval_publishes(VALID_URL, "")

    def test_rejected_add(self):
        """Keep the company without a URL."""
        self._assert_rejection_keeps("", VALID_URL)

    def test_rejected_change(self):
        """Keep the old URL."""
        self._assert_rejection_keeps(VALID_URL, "https://example.com/catalog")

    def test_rejected_removal(self):
        """Keep the existing URL."""
        self._assert_rejection_keeps(VALID_URL, "")

    def test_pending_removal_keeps_the_public_link(self):
        """Show the existing link until a removal is approved."""
        self._start(VALID_URL)
        self._submit_edit("")
        self.client.force_login(self.editor)

        response = self.client.get(reverse("company-view", args=[self.company.pk]))

        self.assertContains(response, self._link(VALID_URL), html=True)


class CompanyPageTests(ProductsPageUrlTestBase):
    """The company page shows the link only when a URL is set."""

    def _page(self, url):
        """Publish a URL and return the company page."""
        self.company.ProductsPageUrl = url
        self.company.save()
        self.client.force_login(self.editor)
        return self.client.get(reverse("company-view", args=[self.company.pk]))

    def test_renders_link_in_new_tab(self):
        """Render the labeled link with the exact href and rel."""
        response = self._page(VALID_URL)

        self.assertContains(response, "Products page URL")
        self.assertContains(response, self._link(VALID_URL), html=True)

    def test_empty_url_renders_no_row(self):
        """Render neither the label nor the link for a blank URL."""
        response = self._page("")

        self.assertNotContains(response, "View products")
        self.assertNotContains(response, "Products page URL")
        self.assertNotContains(response, "ProductsPageUrl")

    def test_escapes_url(self):
        """Escape ampersands, quotes and angle brackets in the href."""
        url = "https://example.com/p?a=1&b=\"2\"&c='3'&d=<x>"
        validate_https_url(url)

        response = self._page(url)

        self.assertContains(
            response,
            'href="https://example.com/p?a=1&amp;b=&quot;2&quot;&amp;c=&#x27;3&#x27;'
            '&amp;d=&lt;x&gt;"',
        )
        self.assertNotContains(response, "<x>")


class ReviewPageTests(ProductsPageUrlTestBase):
    """The review page shows each link with its full destination."""

    def _review(self, change):
        """Return the review page for a change."""
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("company-view-pending", args=[change.pk]))
        self.assertEqual(response.status_code, 200)
        return response

    def _assert_link_with_destination(self, response, url):
        """Assert the link and its full URL as text outside the href."""
        self.assertContains(response, self._link(url), html=True)
        self.assertContains(response, f'<span class="text-break">{url}</span>', html=True)

    def test_edit_shows_current_and_pending_destinations(self):
        """Show both the published and the proposed URL."""
        current = "https://example.com/catalog"
        self.company.ProductsPageUrl = current
        self.company.save()
        change = self._submit_edit(VALID_URL)

        response = self._review(change)

        self._assert_link_with_destination(response, current)
        self._assert_link_with_destination(response, VALID_URL)

    def test_create_shows_pending_destination(self):
        """Show the proposed URL of a new company."""
        pending = PendingCompany.objects.create(
            SrcKey="", Name="New company", Address="", Country="USA",
            ProductsPageUrl=VALID_URL,
        )
        change = PendingChanges.objects.create(
            pending_company=pending, author=self.editor, changeType="create"
        )

        response = self._review(change)

        self._assert_link_with_destination(response, VALID_URL)

    def test_blank_url_renders_empty_cell(self):
        """Render no link for a blank pending value."""
        change = self._submit_edit("")

        response = self._review(change)

        self.assertNotContains(response, "View products")


class ProductsPageUrlUploadTests(UploadTestBase):
    """Bulk upload validates and stages the products page URL column."""

    def _with_urls(self, *urls):
        """Return a valid upload frame with one URL cell per row."""
        dataframe = self._dataframe(len(urls))
        dataframe["ProductsPageUrl"] = list(urls)
        return dataframe

    def test_stages_valid_url(self):
        """Store a valid URL on the staged pending company."""
        import_pending_companies(self._with_urls(VALID_URL))

        self.assertEqual(PendingCompany.objects.get().ProductsPageUrl, VALID_URL)

    def test_rejects_invalid_url_naming_row_and_field(self):
        """Fail the upload with the row number and the field name."""
        for value in INVALID_FORM_URLS:
            with self.subTest(value=value):
                with self.assertRaises(UploadValidationError) as raised:
                    import_pending_companies(self._with_urls(VALID_URL, value))

                self.assertIn("Row 3", str(raised.exception))
                self.assertIn("ProductsPageUrl", str(raised.exception))
                self.assertFalse(PendingCompany.objects.exists())

    def test_blank_cells_are_accepted(self):
        """Treat empty, missing and whitespace cells as no URL."""
        import_pending_companies(self._with_urls("", None, float("nan"), "  "))

        self.assertEqual(
            list(PendingCompany.objects.values_list("ProductsPageUrl", flat=True)),
            ["", "", "", ""],
        )

    def test_upload_without_column_imports(self):
        """Import a file that has no ProductsPageUrl column."""
        dataframe = self._dataframe(1)
        self.assertNotIn("ProductsPageUrl", dataframe.columns)

        import_pending_companies(dataframe)

        self.assertEqual(PendingCompany.objects.get().ProductsPageUrl, "")

    def test_batch_approval_publishes_url(self):
        """Copy the staged URL to the company on batch approval."""
        import_pending_companies(self._with_urls(VALID_URL))
        submit_upload_for_review(self.author, unique_only=False)
        batch = PendingChanges.objects.get().upload_batch

        with self.captureOnCommitCallbacks(execute=True):
            approve_upload_batch(batch)

        self.assertEqual(Company.objects.get().ProductsPageUrl, VALID_URL)

    def test_reads_url_column_from_csv(self):
        """Read the column by its model field name from a CSV upload."""
        dataframe = pd.read_csv(
            StringIO(
                "Name,Country,Status,Industry,Grower,ProductsPageUrl\n"
                f"Acme,USA,{self.status.pk},{self.industry.pk},{self.grower.pk},"
                f"{VALID_URL}\n"
                f"Blank,USA,{self.status.pk},{self.industry.pk},{self.grower.pk},\n"
            )
        )

        import_pending_companies(dataframe)

        self.assertEqual(
            dict(PendingCompany.objects.values_list("Name", "ProductsPageUrl")),
            {"Acme": VALID_URL, "Blank": ""},
        )
