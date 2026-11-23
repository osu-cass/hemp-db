"""Focused tests for spreadsheet parsing and atomic company imports."""

import threading
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

import pandas as pd
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.db.models import QuerySet
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
)
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import (
    Company,
    Grower,
    Industry,
    PendingChanges,
    PendingCompany,
    Status,
    UploadIndex,
)
from .permissions import EDIT_COMPANIES
from .upload import (
    IMPORT_BATCH_SIZE,
    UploadValidationError,
    approve_upload_batch,
    import_pending_companies,
    read_upload_dataframe,
    reject_upload_batch,
    submit_upload_for_review,
    validate_upload_columns,
)
from .views import upload_wizard


class UploadParsingTests(SimpleTestCase):
    """Verify format detection and required-column validation."""

    def test_reads_utf8_csv_with_bom(self):
        """Read a UTF-8 CSV and normalize its header."""
        uploaded_file = SimpleUploadedFile(
            "companies.csv",
            "\ufeffName,Country,Status,Industry,Grower\nAcme,USA,1,2,3\n".encode(),
        )

        dataframe = read_upload_dataframe(uploaded_file)

        self.assertEqual(list(dataframe.columns), ["Name", "Country", "Status", "Industry", "Grower"])
        self.assertEqual(dataframe.iloc[0]["Name"], "Acme")

    def test_reads_csv_with_unexpected_xlsx_extension(self):
        """Treat a text CSV as CSV even when its extension is misleading."""
        uploaded_file = SimpleUploadedFile(
            "companies.xlsx",
            b"Name,Country,Status,Industry,Grower\nAcme,USA,1,2,3\n",
        )

        dataframe = read_upload_dataframe(uploaded_file)

        self.assertEqual(dataframe.iloc[0]["Country"], "USA")

    @patch("helloworld.upload.pd.read_excel")
    def test_reads_xlsx_with_openpyxl_engine(self, read_excel):
        """Use pandas' openpyxl engine for a real XLSX signature."""
        read_excel.return_value = pd.DataFrame(
            [{"Name": "Acme", "Country": "USA", "Status": 1, "Industry": 2, "Grower": 3}]
        )
        uploaded_file = SimpleUploadedFile("companies.xlsx", b"PK\x03\x04workbook")

        read_upload_dataframe(uploaded_file)

        read_excel.assert_called_once_with(uploaded_file, engine="openpyxl")

    def test_reports_missing_required_columns(self):
        """Reject a file before any database import when headers are incomplete."""
        dataframe = pd.DataFrame([{"Name": "Acme"}])

        with self.assertRaisesMessage(
            UploadValidationError,
            "The upload is missing required columns: Country, Grower, Industry, Status.",
        ):
            validate_upload_columns(dataframe)


class UploadWizardTests(TestCase):
    """Keep the staged-company preview bounded and query-efficient."""

    def setUp(self):
        """Create an upload editor for direct view measurements."""
        self.user = get_user_model().objects.create_user(
            username="staff",
            password="password",
            is_staff=True,
        )
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Company),
                codename=EDIT_COMPANIES.rsplit(".", 1)[1],
            )
        )
        self.user.get_all_permissions()
        self.factory = RequestFactory()

    def _stage(self, name):
        """Stage one company and add it to the upload index."""
        company = PendingCompany.objects.create(
            SrcKey="",
            Name=name,
            Address="",
            Country="USA",
        )
        UploadIndex.objects.create(pendingID=str(company.pk))
        return company

    def _get_wizard(self, page=None):
        """Render a wizard page as an upload editor."""
        path = "/upload_wizard" if page is None else f"/upload_wizard?page={page}"
        request = self.factory.get(path)
        request.user = self.user
        return upload_wizard(request)

    def test_marks_duplicates_with_constant_query_count(self):
        """Compute duplicate flags without one query per staged row."""
        Company.objects.create(
            SrcKey="",
            Name="Duplicate",
            Address="",
            Country="USA",
        )
        self._stage("Duplicate")
        self._stage("Unique")

        with self.assertNumQueries(2):
            response = self._get_wizard()

        content = response.content.decode()
        self.assertContains(response, "Duplicate")
        self.assertContains(response, "Unique")
        self.assertIn("table-danger", content)
        self.assertIn("table-success", content)

    def test_paginates_large_staged_uploads(self):
        """Render at most 100 staged companies on each wizard page."""
        for number in range(101):
            self._stage(f"Company {number:03}")

        with self.assertNumQueries(2):
            first_page = self._get_wizard()
        with self.assertNumQueries(2):
            second_page = self._get_wizard(page=2)

        self.assertContains(first_page, "Company 000")
        self.assertContains(first_page, "Company 099")
        self.assertNotContains(first_page, "Company 100")
        self.assertContains(first_page, "Showing 1-100 of 101 staged companies")
        self.assertContains(first_page, 'class="pagination justify-content-center"')
        self.assertInHTML(
            '<li class="page-item disabled"><span class="page-link">First</span></li>',
            first_page.content.decode(),
        )
        self.assertInHTML(
            '<li class="page-item disabled"><span class="page-link">Previous</span></li>',
            first_page.content.decode(),
        )
        self.assertContains(second_page, "Company 100")
        self.assertNotContains(second_page, "Company 000")
        self.assertContains(second_page, "Showing 101-101 of 101 staged companies")
        self.assertInHTML(
            '<li class="page-item disabled"><span class="page-link">Next</span></li>',
            second_page.content.decode(),
        )
        self.assertInHTML(
            '<li class="page-item disabled"><span class="page-link">Last</span></li>',
            second_page.content.decode(),
        )

    def test_submit_buttons_call_the_helper_with_explicit_modes(self):
        """Route each submit action through the matching helper mode."""
        for button, unique_only in (("add-all", False), ("add-unique", True)):
            with self.subTest(button=button):
                request = self.factory.post("/upload_wizard", {button: "1"})
                request.user = self.user
                with (
                    patch(
                        "helloworld.views.submit_upload_for_review", return_value=3
                    ) as submit,
                    patch("helloworld.views.email_upload_reviewers") as notify,
                    patch("helloworld.views.messages.info") as add_message,
                ):
                    response = upload_wizard(request)

                self.assertEqual(response.status_code, 302)
                submit.assert_called_once_with(self.user, unique_only=unique_only)
                notify.assert_called_once_with(3, request.get_host())
                add_message.assert_called_once_with(
                    request, "Submitted 3 companies for review"
                )

    def test_empty_submission_sends_no_notification(self):
        """Skip the reviewer email when no rows reach the review queue."""
        request = self.factory.post("/upload_wizard", {"add-unique": "1"})
        request.user = self.user
        with (
            patch("helloworld.views.submit_upload_for_review", return_value=0),
            patch("helloworld.views.email_upload_reviewers") as notify,
            patch("helloworld.views.messages.info"),
        ):
            upload_wizard(request)

        notify.assert_not_called()

    def test_editor_client_submits_with_csrf_message_and_redirect(self):
        """Submit through the editor and CSRF middleware path without publishing."""
        staged = self._stage("Client Submitted")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(reverse("upload-wizard"))
        csrf_token = client.cookies["csrftoken"].value

        with patch("helloworld.views.email_upload_reviewers"):
            response = client.post(
                reverse("upload-wizard"),
                {"add-all": "1", "csrfmiddlewaretoken": csrf_token},
            )

        self.assertRedirects(response, "/companies", fetch_redirect_response=False)
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            ["Submitted 1 company for review"],
        )
        self.assertFalse(Company.objects.exists())
        change = PendingChanges.objects.get()
        self.assertEqual(change.pending_company, staged)
        self.assertEqual(change.author, self.user)
        self.assertFalse(UploadIndex.objects.exists())


class CompanyImportTestBase(TestCase):
    """Shared reference data and upload-frame builder for import tests."""

    def setUp(self):
        self.status = Status.objects.create(status="Active")
        self.industry = Industry.objects.create(industry="Hemp")
        self.grower = Grower.objects.create(grower="Grower")

    def _dataframe(self, count):
        """Build a valid upload frame reusing the same reference IDs."""
        return pd.DataFrame(
            [
                {
                    "Name": f"Acme {index}",
                    "Country": "USA",
                    "Status": self.status.pk,
                    "Industry": self.industry.pk,
                    "Grower": self.grower.pk,
                }
                for index in range(count)
            ]
        )


class AtomicUploadTests(CompanyImportTestBase):
    """Verify atomic bulk staging of pending companies and upload indexes."""

    def test_invalid_row_does_not_leave_partial_records(self):
        """Roll back previously inserted rows when a later row is invalid."""
        dataframe = pd.DataFrame(
            [
                {
                    "Name": "Acme",
                    "Country": "USA",
                    "Status": self.status.pk,
                    "Industry": self.industry.pk,
                    "Grower": self.grower.pk,
                },
                {
                    "Name": "Broken",
                    "Country": "USA",
                    "Status": 999999,
                    "Industry": self.industry.pk,
                    "Grower": self.grower.pk,
                },
            ]
        )

        with self.assertRaises(UploadValidationError):
            import_pending_companies(dataframe)

        self.assertFalse(PendingCompany.objects.exists())
        self.assertFalse(UploadIndex.objects.exists())

    def test_stages_blank_nullable_decimals_as_null(self):
        """Store missing latitude and longitude cells as null values."""
        dataframe = self._dataframe(1)
        dataframe["Latitude"] = [""]
        dataframe["Longitude"] = [pd.NA]

        company = import_pending_companies(dataframe)[0]

        self.assertIsNone(company.Latitude)
        self.assertIsNone(company.Longitude)

    def test_rejects_fractional_reference_ids(self):
        """Treat a fractional reference cell as invalid instead of truncating it."""
        dataframe = pd.DataFrame(
            [
                {
                    "Name": "Acme",
                    "Country": "USA",
                    "Status": self.status.pk,
                    "Industry": 2.9,
                    "Grower": self.grower.pk,
                }
            ]
        )

        with self.assertRaisesMessage(
            UploadValidationError,
            "Row 2: Industry must contain a valid Industry ID.",
        ):
            import_pending_companies(dataframe)

    def test_rejects_non_finite_reference_ids(self):
        """Reject exponential literals through the row error, not OverflowError."""
        dataframe = pd.DataFrame(
            [
                {
                    "Name": "Acme",
                    "Country": "USA",
                    "Status": self.status.pk,
                    "Industry": "1e309",
                    "Grower": self.grower.pk,
                }
            ]
        )

        with self.assertRaisesMessage(
            UploadValidationError,
            "Row 2: Industry must contain a valid Industry ID.",
        ):
            import_pending_companies(dataframe)

    def test_rejects_boolean_and_malformed_reference_ids(self):
        """Reject boolean and malformed reference cells through the row error."""
        for value in (True, "not-an-id"):
            with self.subTest(value=value):
                dataframe = pd.DataFrame(
                    [
                        {
                            "Name": "Acme",
                            "Country": "USA",
                            "Status": self.status.pk,
                            "Industry": value,
                            "Grower": self.grower.pk,
                        }
                    ]
                )

                with self.assertRaisesMessage(
                    UploadValidationError,
                    "Row 2: Industry must contain a valid Industry ID.",
                ):
                    import_pending_companies(dataframe)

    def test_resolves_integral_float_references(self):
        """Resolve whole-number float cells as pandas emits for numeric columns."""
        dataframe = pd.DataFrame(
            [
                {
                    "Name": "Acme",
                    "Country": "USA",
                    "Status": float(self.status.pk),
                    "Industry": float(self.industry.pk),
                    "Grower": float(self.grower.pk),
                }
            ]
        )

        companies = import_pending_companies(dataframe)

        self.assertEqual(companies[0].Status, self.status)
        self.assertEqual(companies[0].Industry, self.industry)
        self.assertEqual(companies[0].Grower, self.grower)

    def test_stages_rows_in_input_order_with_populated_ids(self):
        """Return persisted companies in input order with primary keys set."""
        companies = import_pending_companies(self._dataframe(3))

        self.assertEqual(
            [company.Name for company in companies], ["Acme 0", "Acme 1", "Acme 2"]
        )
        self.assertTrue(all(company.pk for company in companies))
        self.assertCountEqual(
            PendingCompany.objects.values_list("pk", flat=True),
            [company.pk for company in companies],
        )

    def test_stages_one_upload_index_per_company(self):
        """Key each upload index by its staged company's primary key."""
        companies = import_pending_companies(self._dataframe(3))

        self.assertCountEqual(
            UploadIndex.objects.values_list("pendingID", flat=True),
            [str(company.pk) for company in companies],
        )

    def test_stamps_creation_timestamps_like_save(self):
        """Stamp timestamps the way CompanyDetail.save() does for new rows."""
        started = timezone.now()
        companies = import_pending_companies(self._dataframe(2))
        finished = timezone.now()

        # bulk_create bypasses save(), but must produce its observable result:
        # both columns stamped during the import, lastUpdated never before dateCreated.
        self.assertTrue(
            all(
                started <= company.dateCreated <= company.lastUpdated <= finished
                for company in companies
            )
        )

    def test_clears_import_batch_id_after_staging(self):
        """Leave no correlation token behind in the database or returned rows."""
        companies = import_pending_companies(self._dataframe(2))

        self.assertFalse(PendingCompany.objects.filter(import_batch_id__isnull=False).exists())
        self.assertTrue(all(company.import_batch_id is None for company in companies))

    def test_multiple_batches_stage_identically(self):
        """Split inserts across batches without losing or reordering rows."""
        with patch("helloworld.upload.IMPORT_BATCH_SIZE", 1):
            companies = import_pending_companies(self._dataframe(3))

        self.assertEqual(
            list(PendingCompany.objects.order_by("pk").values_list("Name", flat=True)),
            [company.Name for company in companies],
        )

    def test_upload_index_failure_rolls_back_staged_companies(self):
        """Roll back pending-company inserts when upload-index staging fails."""
        dataframe = self._dataframe(2)

        with (
            patch.object(
                UploadIndex.objects,
                "bulk_create",
                side_effect=IntegrityError("UploadIndex insert failed."),
            ),
            self.assertRaises(IntegrityError),
        ):
            import_pending_companies(dataframe)

        self.assertFalse(PendingCompany.objects.exists())
        self.assertFalse(UploadIndex.objects.exists())


class ImportQueryTests(CompanyImportTestBase):
    """Verify reference prefetching and bounded statement counts."""

    def test_reference_lookups_run_once_per_model(self):
        """Issue one lookup per reference model instead of one per row."""
        dataframe = self._dataframe(5)

        with (
            patch.object(
                Status.objects, "in_bulk", side_effect=Status.objects.in_bulk
            ) as status_lookup,
            patch.object(
                Industry.objects, "in_bulk", side_effect=Industry.objects.in_bulk
            ) as industry_lookup,
            patch.object(
                Grower.objects, "in_bulk", side_effect=Grower.objects.in_bulk
            ) as grower_lookup,
        ):
            import_pending_companies(dataframe)

        status_lookup.assert_called_once()
        industry_lookup.assert_called_once()
        grower_lookup.assert_called_once()

    def test_row_count_does_not_increase_statement_count(self):
        """Keep statements flat for uploads smaller than one batch."""
        self.assertLess(10, IMPORT_BATCH_SIZE)

        def staged_statements(row_count):
            """Return the SQL statement count for staging the requested rows."""
            with CaptureQueriesContext(connection) as context:
                import_pending_companies(self._dataframe(row_count))
            return len(context.captured_queries)

        single_row = staged_statements(1)
        multi_row = staged_statements(10)

        self.assertEqual(multi_row, single_row)


class UploadTestBase(CompanyImportTestBase):
    """Stage indexed companies on behalf of an upload author."""

    def setUp(self):
        """Create the upload author alongside the shared reference data."""
        super().setUp()
        self.author = get_user_model().objects.create_user(
            username="uploader", password="password"
        )

    def _stage(self, name, **values):
        """Create one indexed pending company with valid reference fields."""
        defaults = {
            "SrcKey": "source-key",
            "Name": name,
            "Industry": self.industry,
            "Status": self.status,
            "Grower": self.grower,
            "Address": "123 Main Street",
            "Country": "USA",
        }
        defaults.update(values)
        company = PendingCompany.objects.create(**defaults)
        UploadIndex.objects.create(pendingID=str(company.pk))
        return company


class UploadSubmissionTests(UploadTestBase):
    """Verify staged uploads become pending create changes."""

    def test_add_all_submits_every_row_including_duplicates(self):
        """Queue every indexed row, including duplicate names, for review."""
        existing = Company.objects.create(
            SrcKey="", Name="Existing", Address="", Country="USA"
        )
        staged = [
            self._stage(existing.Name),
            self._stage("Repeated"),
            self._stage("Repeated"),
        ]

        submitted = submit_upload_for_review(self.author, unique_only=False)

        self.assertEqual(submitted, len(staged))
        changes = list(PendingChanges.objects.order_by("pk"))
        self.assertEqual(
            [change.pending_company_id for change in changes],
            [company.pk for company in staged],
        )
        for change in changes:
            self.assertEqual(change.changeType, "create")
            self.assertEqual(change.author, self.author)
            self.assertEqual(change.status, PendingChanges.PendingStatus.PENDING)
        self.assertIsNotNone(changes[0].upload_batch)
        self.assertEqual({change.upload_batch for change in changes}, {changes[0].upload_batch})
        self.assertEqual(list(Company.objects.all()), [existing])
        self.assertFalse(UploadIndex.objects.exists())

        self.assertEqual(submit_upload_for_review(self.author, unique_only=False), 0)

    def test_add_unique_uses_database_name_equality_and_first_pk(self):
        """Skip database-equivalent names, keep the first row, and discard the rest."""
        Company.objects.create(SrcKey="", Name="Existing", Address="", Country="USA")
        self._stage("existing")  # Case-insensitive match on the existing name.
        first = self._stage("Upload Name")
        self._stage("upload name")  # Database-equal duplicate; first row wins.
        different = self._stage("Different Name")

        submitted = submit_upload_for_review(self.author, unique_only=True)

        self.assertEqual(submitted, 2)
        self.assertEqual(
            list(
                PendingChanges.objects.order_by("pk").values_list(
                    "pending_company__Name", flat=True
                )
            ),
            ["Upload Name", "Different Name"],
        )
        self.assertCountEqual(
            PendingCompany.objects.values_list("pk", flat=True),
            [first.pk, different.pk],
        )
        self.assertFalse(UploadIndex.objects.exists())

    def test_separate_uploads_get_separate_batches(self):
        """Give each finished upload its own batch identifier."""
        self._stage("First Upload")
        submit_upload_for_review(self.author, unique_only=False)
        self._stage("Second Upload")
        submit_upload_for_review(self.author, unique_only=False)

        self.assertEqual(
            PendingChanges.objects.values("upload_batch").distinct().count(), 2
        )

    def test_failure_after_insert_rolls_back_the_submission(self):
        """Keep staging rows and queue nothing when cleanup fails."""
        staged = self._stage("Rollback Company")

        with (
            patch.object(
                UploadIndex.objects,
                "all",
                side_effect=IntegrityError("Upload-index cleanup failed."),
            ),
            self.assertRaises(IntegrityError),
        ):
            submit_upload_for_review(self.author, unique_only=False)

        self.assertFalse(PendingChanges.objects.exists())
        self.assertTrue(PendingCompany.objects.filter(pk=staged.pk).exists())
        self.assertTrue(UploadIndex.objects.filter(pendingID=str(staged.pk)).exists())


class UploadBatchDecisionTests(UploadTestBase):
    """Verify set-based approval and rejection of submitted uploads."""

    def _submit(self, *names, **values):
        """Stage and submit companies, returning their upload batch."""
        for name in names:
            self._stage(name, **values)
        submit_upload_for_review(self.author, unique_only=False)
        return PendingChanges.objects.latest("pk").upload_batch

    def _statuses(self, batch):
        """Return the review statuses of one upload batch."""
        return set(
            PendingChanges.objects.filter(upload_batch=batch).values_list(
                "status", flat=True
            )
        )

    def test_approval_publishes_only_the_batch_and_invalidates_the_map(self):
        """Promote one batch and leave other uploads pending."""
        batch = self._submit("Batch One", "Batch Two")
        other = self._submit("Other Upload")

        with patch("helloworld.upload.invalidate_map_cache") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                approved = approve_upload_batch(batch)

        self.assertEqual(approved, 2)
        self.assertCountEqual(
            Company.objects.values_list("Name", flat=True), ["Batch One", "Batch Two"]
        )
        self.assertEqual(self._statuses(batch), {PendingChanges.PendingStatus.APPROVED})
        self.assertEqual(self._statuses(other), {PendingChanges.PendingStatus.PENDING})
        invalidate.assert_called_once_with(sender=Company)

        self.assertEqual(approve_upload_batch(batch), 0)

    def test_approval_skips_rows_already_decided(self):
        """Leave rows a reviewer already decided one at a time."""
        batch = self._submit("Decided Alone", "Still Pending")
        PendingChanges.objects.filter(pending_company__Name="Decided Alone").update(
            status=PendingChanges.PendingStatus.REJECTED
        )

        with self.captureOnCommitCallbacks(execute=True):
            approved = approve_upload_batch(batch)

        self.assertEqual(approved, 1)
        self.assertEqual(
            list(Company.objects.values_list("Name", flat=True)), ["Still Pending"]
        )

    def test_rejection_marks_pending_rows_without_publishing(self):
        """Reject every pending row in a batch without creating companies."""
        batch = self._submit("Reject One", "Reject Two")

        rejected = reject_upload_batch(batch)

        self.assertEqual(rejected, 2)
        self.assertEqual(self._statuses(batch), {PendingChanges.PendingStatus.REJECTED})
        self.assertFalse(Company.objects.exists())
        self.assertEqual(reject_upload_batch(batch), 0)

    def test_copies_scalar_values_foreign_keys_and_timestamps(self):
        """Copy concrete values and preserve creation time during approval."""
        date_created = timezone.now() - timedelta(days=2)
        batch = self._submit(
            "Full Company",
            SrcKey="source-123",
            Address="456 Market Street",
            Sales="Sales value",
            Country="Canada",
            Latitude=Decimal("45.123456"),
            Longitude=Decimal("-122.123456"),
            dateCreated=date_created,
        )
        staged = PendingCompany.objects.get(Name="Full Company")
        started = timezone.now()

        with self.captureOnCommitCallbacks(execute=True):
            approved = approve_upload_batch(batch)

        finished = timezone.now()
        company = Company.objects.get(Name=staged.Name)
        self.assertEqual(approved, 1)
        self.assertEqual(company.SrcKey, staged.SrcKey)
        self.assertEqual(company.Address, staged.Address)
        self.assertEqual(company.Sales, staged.Sales)
        self.assertEqual(company.Country, staged.Country)
        self.assertEqual(company.Latitude, staged.Latitude)
        self.assertEqual(company.Longitude, staged.Longitude)
        self.assertEqual(company.Industry_id, self.industry.pk)
        self.assertEqual(company.Status_id, self.status.pk)
        self.assertEqual(company.Grower_id, self.grower.pk)
        self.assertEqual(company.dateCreated, date_created)
        self.assertTrue(started <= company.lastUpdated <= finished)

    def test_approval_stamps_every_promoted_company(self):
        """Stamp every promoted company during the approval window."""
        batch = self._submit("Timestamp One", "Timestamp Two")
        started = timezone.now()

        with self.captureOnCommitCallbacks(execute=True):
            approve_upload_batch(batch)

        finished = timezone.now()
        timestamps = list(Company.objects.values_list("lastUpdated", flat=True))
        self.assertEqual(len(timestamps), 2)
        self.assertTrue(
            all(started <= timestamp <= finished for timestamp in timestamps)
        )

    def test_failure_after_insert_rolls_back_everything_and_cache(self):
        """Roll back promotion and keep the batch pending when marking fails."""
        batch = self._submit("Rollback Company")

        with (
            patch.object(
                QuerySet, "update", side_effect=IntegrityError("Status update failed.")
            ),
            patch("helloworld.upload.invalidate_map_cache") as invalidate,
            self.captureOnCommitCallbacks(execute=True) as callbacks,
            self.assertRaises(IntegrityError),
        ):
            approve_upload_batch(batch)

        self.assertFalse(Company.objects.exists())
        self.assertEqual(self._statuses(batch), {PendingChanges.PendingStatus.PENDING})
        self.assertEqual(callbacks, [])
        invalidate.assert_not_called()

    @skipUnless(connection.vendor == "mysql", "Requires MySQL batch-size behavior.")
    def test_approval_company_inserts_are_batch_bounded(self):
        """Keep company inserts flat through 500 rows and batch beyond it."""
        def approval_statements(row_count):
            """Return total and company-insert SQL counts for one approval."""
            batch = self._submit(
                *(f"Batch Company {row_count}-{index}" for index in range(row_count))
            )
            with CaptureQueriesContext(connection) as context:
                approve_upload_batch(batch)
            company_inserts = sum(
                query["sql"].lower().startswith("insert into `company`")
                for query in context.captured_queries
            )
            return len(context.captured_queries), company_inserts

        one_row, one_row_inserts = approval_statements(1)
        one_batch, one_batch_inserts = approval_statements(IMPORT_BATCH_SIZE)
        two_batches, two_batch_inserts = approval_statements(IMPORT_BATCH_SIZE + 1)

        self.assertEqual(one_batch_inserts, one_row_inserts)
        self.assertEqual(two_batch_inserts, one_batch_inserts + 1)
        self.assertLess(one_batch, one_row + 50)
        self.assertLess(two_batches, one_batch + 50)


class ApprovalConcurrencyTests(TransactionTestCase):
    """Verify duplicate batch approvals serialize on pending-change rows."""

    @skipUnless(connection.vendor == "mysql", "Requires MySQL row locking.")
    def test_duplicate_approvals_serialize(self):
        """Block the second approval until the first transaction commits."""
        author = get_user_model().objects.create_user(
            username="uploader", password="password"
        )
        staged = PendingCompany.objects.create(
            SrcKey="",
            Name="Concurrent Approval",
            Address="",
            Country="USA",
        )
        UploadIndex.objects.create(pendingID=str(staged.pk))
        submit_upload_for_review(author, unique_only=False)
        batch = PendingChanges.objects.get().upload_batch
        first_inside = threading.Event()
        release_first = threading.Event()
        second_select_started = threading.Event()
        second_done = threading.Event()
        results = {}
        errors = []

        def first_approval():
            close_old_connections()
            try:
                with transaction.atomic():
                    results["first"] = approve_upload_batch(batch)
                    first_inside.set()
                    if not release_first.wait(10):
                        raise TimeoutError("First approval was not released.")
            except Exception as error:  # pragma: no cover - reported by assertion
                errors.append(("first", error))
            finally:
                connections["default"].close()

        def second_approval():
            close_old_connections()
            thread_connection = connections["default"]

            def mark_locking_select(execute, sql, params, many, context):
                if "FOR UPDATE" in sql.upper() and "pending_change" in sql.lower():
                    second_select_started.set()
                return execute(sql, params, many, context)

            try:
                with thread_connection.execute_wrapper(mark_locking_select):
                    results["second"] = approve_upload_batch(batch)
            except Exception as error:  # pragma: no cover - reported by assertion
                errors.append(("second", error))
            finally:
                second_done.set()
                thread_connection.close()

        first_thread = threading.Thread(target=first_approval)
        second_thread = threading.Thread(target=second_approval)
        first_thread.start()
        try:
            self.assertTrue(first_inside.wait(10))
            second_thread.start()
            self.assertTrue(second_select_started.wait(10))
            self.assertFalse(second_done.wait(0.5))
        finally:
            release_first.set()
            first_thread.join(10)
            if second_thread.ident is not None:
                second_thread.join(10)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, {"first": 1, "second": 0})
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(
            PendingChanges.objects.get().status, PendingChanges.PendingStatus.APPROVED
        )
