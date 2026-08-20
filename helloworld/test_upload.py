"""Focused tests for spreadsheet parsing and atomic company imports."""

from unittest.mock import patch

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from .models import Grower, Industry, PendingCompany, Status, UploadIndex
from .upload import (
    UploadValidationError,
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


class AtomicUploadTests(TestCase):
    """Verify that one invalid row rolls back the whole import."""

    def setUp(self):
        self.status = Status.objects.create(status="Active")
        self.industry = Industry.objects.create(industry="Hemp")
        self.grower = Grower.objects.create(grower="Grower")

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
