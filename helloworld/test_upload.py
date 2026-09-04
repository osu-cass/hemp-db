"""Focused tests for spreadsheet parsing, staging, and batch review."""

import threading
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

import pandas as pd
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections, transaction
from django.db.models.deletion import ProtectedError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .admin import CompanyUploadBatchAdmin
from .models import (
    Company,
    CompanyUploadBatch,
    Grower,
    Industry,
    PendingChanges,
    PendingCompany,
    Solution,
    Status,
)
from .upload import (
    IMPORT_BATCH_SIZE,
    UploadValidationError,
    approve_pending_companies,
    import_pending_companies,
    read_upload_dataframe,
    validate_upload_columns,
)


class UploadParsingTests(SimpleTestCase):
    """Verify format detection and required-column validation."""

    def test_reads_utf8_csv_with_bom(self):
        """Read a UTF-8 CSV and normalize its header."""
        uploaded_file = SimpleUploadedFile(
            "companies.csv",
            "\ufeffName,Country,Status,Industry,Grower\nAcme,USA,1,2,3\n".encode(),
        )

        dataframe = read_upload_dataframe(uploaded_file)

        self.assertEqual(
            list(dataframe.columns), ["Name", "Country", "Status", "Industry", "Grower"]
        )
        self.assertEqual(dataframe.iloc[0]["Name"], "Acme")

    def test_reads_csv_with_unexpected_xlsx_extension(self):
        """Treat a text CSV as CSV when its extension is misleading."""
        uploaded_file = SimpleUploadedFile(
            "companies.xlsx",
            b"Name,Country,Status,Industry,Grower\nAcme,USA,1,2,3\n",
        )

        dataframe = read_upload_dataframe(uploaded_file)

        self.assertEqual(dataframe.iloc[0]["Country"], "USA")

    @patch("helloworld.upload.pd.read_excel")
    def test_reads_xlsx_with_openpyxl_engine(self, read_excel):
        """Use pandas' openpyxl engine for an XLSX signature."""
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


class CompanyImportTestBase(TestCase):
    """Shared reference data and upload-frame builders."""

    def setUp(self):
        """Create valid foreign-key reference rows."""
        self.status = Status.objects.create(status="Active")
        self.industry = Industry.objects.create(industry="Hemp")
        self.grower = Grower.objects.create(grower="Grower")

    def _dataframe(self, count):
        """Build a valid upload frame in input order."""
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
    """Verify atomic, batch-scoped staging."""

    def test_invalid_row_does_not_leave_partial_records_or_a_batch(self):
        """Roll back a batch when a later row is invalid."""
        dataframe = self._dataframe(2)
        dataframe.loc[1, "Status"] = 999999

        with self.assertRaises(UploadValidationError):
            import_pending_companies(dataframe)

        self.assertFalse(PendingCompany.objects.exists())
        self.assertFalse(CompanyUploadBatch.objects.exists())

    def test_stages_rows_in_input_order_with_populated_ids(self):
        """Return persisted companies linked to one batch in input order."""
        companies = import_pending_companies(self._dataframe(3))

        self.assertEqual(
            [company.Name for company in companies], ["Acme 0", "Acme 1", "Acme 2"]
        )
        self.assertTrue(all(company.pk for company in companies))
        self.assertEqual(CompanyUploadBatch.objects.count(), 1)
        self.assertEqual(companies[0].upload_batch_id, companies[1].upload_batch_id)

    def test_stamps_creation_timestamps_like_save(self):
        """Stamp staged rows with ordered creation and update timestamps."""
        started = timezone.now()

        companies = import_pending_companies(self._dataframe(2))

        finished = timezone.now()
        self.assertTrue(
            all(
                started <= company.dateCreated <= company.lastUpdated <= finished
                for company in companies
            )
        )

    def test_stages_blank_nullable_decimals_as_null(self):
        """Store missing latitude and longitude cells as null values."""
        dataframe = self._dataframe(1)
        dataframe["Latitude"] = [""]
        dataframe["Longitude"] = [pd.NA]

        company = import_pending_companies(dataframe)[0]

        self.assertIsNone(company.Latitude)
        self.assertIsNone(company.Longitude)

    def test_resolves_integral_float_references(self):
        """Resolve whole-number float cells as pandas emits for numeric columns."""
        dataframe = self._dataframe(1).astype(
            {"Status": float, "Industry": float, "Grower": float}
        )

        company = import_pending_companies(dataframe)[0]

        self.assertEqual(company.Status, self.status)
        self.assertEqual(company.Industry, self.industry)
        self.assertEqual(company.Grower, self.grower)

    def test_reference_lookups_run_once_per_model(self):
        """Issue one lookup per reference model instead of one per row."""
        dataframe = self._dataframe(5)

        with (
            patch.object(Status.objects, "in_bulk", wraps=Status.objects.in_bulk) as status_lookup,
            patch.object(Industry.objects, "in_bulk", wraps=Industry.objects.in_bulk) as industry_lookup,
            patch.object(Grower.objects, "in_bulk", wraps=Grower.objects.in_bulk) as grower_lookup,
        ):
            import_pending_companies(dataframe)

        status_lookup.assert_called_once()
        industry_lookup.assert_called_once()
        grower_lookup.assert_called_once()

    def test_staging_statement_count_is_flat_for_small_batches(self):
        """Keep reference query count independent of row count."""
        def statement_count(row_count):
            """Return the number of SQL statements used to stage rows."""
            with CaptureQueriesContext(connection) as context:
                import_pending_companies(self._dataframe(row_count))
            return len(context.captured_queries)

        self.assertEqual(statement_count(1), statement_count(10))


class UploadBatchSafetyTests(CompanyImportTestBase):
    """Protect staged rows and review metadata from accidental admin changes."""

    def test_batch_cannot_be_deleted_while_rows_are_staged(self):
        """Reject deleting a batch that still owns staged rows."""
        batch = CompanyUploadBatch.objects.create(original_filename="test.csv")
        PendingCompany.objects.create(
            upload_batch=batch,
            SrcKey="source-key",
            Name="Staged",
            Industry=self.industry,
            Status=self.status,
            Grower=self.grower,
            Address="123 Main Street",
            Country="USA",
        )

        with self.assertRaises(ProtectedError):
            batch.delete()

        self.assertTrue(CompanyUploadBatch.objects.filter(pk=batch.pk).exists())

    def test_batch_admin_is_read_only(self):
        """Allow permitted Staff users to inspect batches but not mutate them."""
        model_admin = CompanyUploadBatchAdmin(CompanyUploadBatch, admin.site)
        request = RequestFactory().get("/admin/helloworld/companyuploadbatch/")

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))


class AdminAccessTests(TestCase):
    """Verify the built-in admin site's required user flags."""

    def setUp(self):
        """Create a request used for direct admin-site checks."""
        self.admin_site = admin.AdminSite()
        self.request = RequestFactory().get("/admin/")

    def _has_access(self, *, is_active=True, is_staff=False, is_superuser=False):
        """Return admin access for a user with the supplied flags."""
        user = get_user_model().objects.create_user(
            username=f"admin-{get_user_model().objects.count()}",
            is_active=is_active,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        self.request.user = user
        return self.admin_site.has_permission(self.request)

    def test_denies_superuser_without_staff_flag(self):
        """Require the staff checkbox in addition to superuser."""
        self.assertFalse(self._has_access(is_superuser=True))

    def test_denies_inactive_staff_superuser(self):
        """Require active status in addition to both role flags."""
        self.assertFalse(
            self._has_access(is_active=False, is_staff=True, is_superuser=True)
        )

    def test_allows_active_staff_without_superuser(self):
        """Allow active Staff users into the standard admin site."""
        self.assertTrue(self._has_access(is_staff=True))

    def test_allows_active_staff_superuser(self):
        """Allow a user with all required admin flags."""
        self.assertTrue(self._has_access(is_staff=True, is_superuser=True))


class PendingCompanyApprovalTests(CompanyImportTestBase):
    """Verify set-based promotion and cleanup for one batch."""

    def _batch(self, *names):
        """Create a pending upload batch with valid rows."""
        batch = CompanyUploadBatch.objects.create(original_filename="test.csv")
        PendingCompany.objects.bulk_create(
            [
                PendingCompany(
                    upload_batch=batch,
                    SrcKey="source-key",
                    Name=name,
                    Industry=self.industry,
                    Status=self.status,
                    Grower=self.grower,
                    Address="123 Main Street",
                    Country="USA",
                )
                for name in names
            ]
        )
        return batch

    def test_add_all_promotes_only_the_selected_batch(self):
        """Promote every row in one batch and leave another pending."""
        first = self._batch("First", "Repeated", "Repeated")
        second = self._batch("Second")

        with patch("helloworld.upload.invalidate_map_cache") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                created = approve_pending_companies(
                    unique_only=False, batch=first, reviewer=None
                )

        self.assertEqual(created, 3)
        self.assertEqual(Company.objects.count(), 3)
        self.assertEqual(PendingCompany.objects.filter(upload_batch=second).count(), 1)
        self.assertEqual(
            CompanyUploadBatch.objects.get(pk=first.pk).status,
            CompanyUploadBatch.Status.APPROVED,
        )
        self.assertEqual(
            CompanyUploadBatch.objects.get(pk=first.pk).review_mode,
            CompanyUploadBatch.ReviewMode.ALL,
        )
        invalidate.assert_called_once_with(sender=Company)

    def test_add_unique_uses_first_row_and_database_existing_names(self):
        """Skip existing names and duplicate staged names within one batch."""
        Company.objects.create(
            SrcKey="", Name="Existing", Address="", Country="USA"
        )
        batch = self._batch("Existing", "Upload Name", "Upload Name", "Different")

        created = approve_pending_companies(
            unique_only=True, batch=batch, reviewer=None
        )

        self.assertEqual(created, 2)
        self.assertEqual(
            list(Company.objects.order_by("pk").values_list("Name", flat=True)),
            ["Existing", "Upload Name", "Different"],
        )

    def test_approval_copies_fields_and_preserves_creation_time(self):
        """Copy scalar and foreign-key values while stamping approval time."""
        date_created = timezone.now() - timedelta(days=2)
        batch = CompanyUploadBatch.objects.create(original_filename="test.csv")
        staged = PendingCompany.objects.create(
            upload_batch=batch,
            SrcKey="source-123",
            Name="Full Company",
            Industry=self.industry,
            Status=self.status,
            Grower=self.grower,
            Address="456 Market Street",
            Sales="Sales value",
            Country="Canada",
            Latitude=Decimal("45.123456"),
            Longitude=Decimal("-122.123456"),
            dateCreated=date_created,
        )
        started = timezone.now()

        with self.captureOnCommitCallbacks(execute=True):
            created = approve_pending_companies(
                unique_only=False, batch=batch, reviewer=None
            )

        finished = timezone.now()
        company = Company.objects.get(Name=staged.Name)
        self.assertEqual(created, 1)
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
        """Stamp each promoted company during the approval window."""
        batch = self._batch("Timestamp One", "Timestamp Two")
        started = timezone.now()

        with self.captureOnCommitCallbacks(execute=True):
            approve_pending_companies(unique_only=False, batch=batch, reviewer=None)

        finished = timezone.now()
        timestamps = list(
            Company.objects.order_by("pk").values_list("lastUpdated", flat=True)
        )
        self.assertEqual(len(timestamps), 2)
        self.assertTrue(
            all(started <= timestamp <= finished for timestamp in timestamps)
        )

    def test_approval_cleans_related_pending_rows(self):
        """Delete staged many-to-many and pending-change rows after approval."""
        existing = Company.objects.create(
            SrcKey="", Name="Existing", Address="", Country="USA"
        )
        batch = self._batch("Related Pending")
        staged = PendingCompany.objects.get(upload_batch=batch)
        solution = Solution.objects.create(solution="Fiber")
        staged.Solutions.add(solution)
        PendingChanges.objects.create(
            company=existing,
            pending_company=staged,
            changeType="edit",
        )

        with self.captureOnCommitCallbacks(execute=True):
            approve_pending_companies(unique_only=False, batch=batch, reviewer=None)

        self.assertFalse(PendingChanges.objects.exists())
        self.assertFalse(PendingCompany.Solutions.through.objects.exists())
        self.assertTrue(Company.objects.filter(Name=staged.Name).exists())

    def test_unique_without_new_companies_does_not_invalidate_cache(self):
        """Skip existing names without registering a cache callback."""
        Company.objects.create(
            SrcKey="", Name="Existing", Address="", Country="USA"
        )
        batch = self._batch("Existing")

        with patch("helloworld.upload.invalidate_map_cache") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                created = approve_pending_companies(
                    unique_only=True, batch=batch, reviewer=None
                )

        self.assertEqual(created, 0)
        invalidate.assert_not_called()
        self.assertEqual(Company.objects.count(), 1)
        self.assertFalse(PendingCompany.objects.exists())

    def test_approval_failure_rolls_back_company_and_cache_changes(self):
        """Roll back promoted rows and the cache callback on review failure."""
        batch = self._batch("Rollback Company")

        with (
            patch(
                "helloworld.upload._mark_batch_reviewed",
                side_effect=RuntimeError("review bookkeeping failed"),
            ),
            patch("helloworld.upload.invalidate_map_cache") as invalidate,
            self.captureOnCommitCallbacks(execute=True) as callbacks,
            self.assertRaises(RuntimeError),
        ):
            approve_pending_companies(unique_only=False, batch=batch, reviewer=None)

        self.assertFalse(Company.objects.exists())
        self.assertTrue(PendingCompany.objects.filter(upload_batch=batch).exists())
        batch.refresh_from_db()
        self.assertEqual(batch.status, CompanyUploadBatch.Status.PENDING)
        self.assertEqual(callbacks, [])
        invalidate.assert_not_called()

    @skipUnless(connection.vendor == "mysql", "Requires MySQL batch-size behavior.")
    def test_approval_company_inserts_are_batch_bounded(self):
        """Keep company inserts bounded by the configured import batch size."""
        def approval_statements(row_count):
            """Return total and company-insert SQL counts for one approval."""
            batch = self._batch(
                *(f"Batch Company {row_count}-{index}" for index in range(row_count))
            )
            with CaptureQueriesContext(connection) as context:
                approve_pending_companies(
                    unique_only=False, batch=batch, reviewer=None
                )
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

    def test_cancel_removes_rows_and_records_reviewer(self):
        """Cancel a pending batch without affecting other company data."""
        reviewer = get_user_model().objects.create_user(username="manager")
        batch = self._batch("Canceled")

        from .upload import cancel_upload_batch

        self.assertTrue(cancel_upload_batch(batch, reviewer))
        batch.refresh_from_db()
        self.assertEqual(batch.status, CompanyUploadBatch.Status.CANCELED)
        self.assertEqual(batch.reviewer, reviewer)
        self.assertFalse(PendingCompany.objects.filter(upload_batch=batch).exists())


class ApprovalConcurrencyTests(TransactionTestCase):
    """Verify concurrent reviews serialize on the batch row."""

    @skipUnless(connection.vendor == "mysql", "Requires MySQL row locking.")
    def test_duplicate_approvals_serialize(self):
        """Block the second approval until the first transaction commits."""
        status = Status.objects.create(status="Active")
        industry = Industry.objects.create(industry="Hemp")
        grower = Grower.objects.create(grower="Grower")
        batch = CompanyUploadBatch.objects.create(original_filename="test.csv")
        PendingCompany.objects.create(
            upload_batch=batch,
            SrcKey="",
            Name="Concurrent Approval",
            Address="",
            Country="USA",
            Status=status,
            Industry=industry,
            Grower=grower,
        )
        first_inside = threading.Event()
        release_first = threading.Event()
        second_select_started = threading.Event()
        second_done = threading.Event()
        results = {}
        errors = []

        def first_approval():
            """Run the first approval while holding its outer transaction."""
            close_old_connections()
            try:
                with transaction.atomic():
                    results["first"] = approve_pending_companies(
                        unique_only=False, batch=batch
                    )
                    first_inside.set()
                    if not release_first.wait(10):
                        raise TimeoutError("First approval was not released.")
            except Exception as error:  # pragma: no cover - reported by assertion
                errors.append(("first", error))
            finally:
                connections["default"].close()

        def second_approval():
            """Run a second approval and observe its blocking lock query."""
            close_old_connections()
            thread_connection = connections["default"]

            def mark_locking_select(execute, sql, params, many, context):
                """Signal when the second transaction requests the batch lock."""
                if "FOR UPDATE" in sql.upper() and "companyuploadbatch" in sql.lower():
                    second_select_started.set()
                return execute(sql, params, many, context)

            try:
                with thread_connection.execute_wrapper(mark_locking_select):
                    results["second"] = approve_pending_companies(
                        unique_only=False, batch=batch
                    )
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
        self.assertEqual(results, {"first": 1, "second": None})
        self.assertEqual(Company.objects.count(), 1)
        self.assertFalse(PendingCompany.objects.exists())


class LegacyUploadMigrationTests(TransactionTestCase):
    """Verify old upload-index rows are preserved during the schema upgrade."""

    def test_legacy_rows_move_to_one_reviewer_visible_batch(self):
        """Attach legacy staged rows to one pending batch and remove the queue."""
        from django.db.migrations.executor import MigrationExecutor

        migrate_from = ("helloworld", "0018_pendingcompany_import_batch_id")
        migrate_to = ("helloworld", "0019_permissions_upload_batches")
        executor = MigrationExecutor(connection)
        executor.migrate([migrate_from])
        old_apps = executor.loader.project_state(migrate_from, at_end=True).apps
        pending_model = old_apps.get_model("helloworld", "PendingCompany")
        index_model = old_apps.get_model("helloworld", "UploadIndex")
        pending = pending_model.objects.create(
            SrcKey="", Name="Legacy", Address="", Country="USA"
        )
        index_model.objects.create(pendingID=str(pending.pk))

        executor = MigrationExecutor(connection)
        executor.migrate([migrate_to])
        batch = CompanyUploadBatch.objects.get()

        self.assertEqual(batch.original_filename, "legacy staged upload")
        self.assertIsNone(batch.uploader_id)
        self.assertEqual(batch.status, CompanyUploadBatch.Status.PENDING)
        self.assertEqual(PendingCompany.objects.get(pk=pending.pk).upload_batch_id, batch.pk)
        self.assertNotIn("UploadIndex", connection.introspection.table_names())
