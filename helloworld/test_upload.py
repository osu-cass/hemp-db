"""Focused tests for spreadsheet parsing and atomic company imports."""

from inspect import unwrap
from unittest.mock import patch

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .models import Company, Grower, Industry, PendingCompany, Status, UploadIndex
from .upload import (
    IMPORT_BATCH_SIZE,
    UploadValidationError,
    import_pending_companies,
    read_upload_dataframe,
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
        """Create a staff request factory for direct view measurements."""
        self.user = get_user_model().objects.create_user(
            username="staff",
            password="password",
            is_staff=True,
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
        """Render a wizard page as a staff user."""
        path = "/upload_wizard" if page is None else f"/upload_wizard?page={page}"
        request = self.factory.get(path)
        request.user = self.user
        return unwrap(upload_wizard)(request)

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
        self.assertContains(second_page, "Company 100")
        self.assertNotContains(second_page, "Company 000")
        self.assertContains(second_page, "Showing 101-101 of 101 staged companies")


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
