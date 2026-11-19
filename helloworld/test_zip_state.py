"""Tests for the ZIP field and USPS State codes."""

import csv
import importlib
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from unittest.mock import patch

import pandas as pd
from django.apps import apps
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .locations import STATE_MESSAGE, ZIP_MESSAGE, clean_location, is_us_country, usps_state_code
from .models import Company, PendingChanges, PendingCompany
from .permissions import EDIT_COMPANIES
from .test_support import CompanyWorkflowHelpers
from .test_upload import UploadTestBase
from .upload import UploadValidationError, import_pending_companies, read_upload_dataframe
from .views import check_if_location_edited

migration = importlib.import_module("helloworld.migrations.0023_zip_and_usps_state")


class LocationRuleTests(SimpleTestCase):
    """The shared rules map State names and check ZIP format."""

    def test_us_country_aliases(self):
        """Accept USA, US and United States in any case or punctuation."""
        for country in ("USA", "us", "U.S.A.", "United States", " united  states "):
            with self.subTest(country=country):
                self.assertTrue(is_us_country(country))
        for country in ("Canada", "--", "", None, "United Kingdom"):
            with self.subTest(country=country):
                self.assertFalse(is_us_country(country))

    def test_state_codes_and_names(self):
        """Map USPS codes, full names and DC spellings to the code."""
        cases = {
            "OR": "OR", "or": "OR", "Oregon": "OR", " north  carolina ": "NC",
            "Washington, D.C.": "DC", "District of Columbia": "DC", "Puerto Rico": "PR",
        }
        for value, code in cases.items():
            with self.subTest(value=value):
                self.assertEqual(usps_state_code(value), code)
        for value in ("Ontario", "Washington/Arizona", "XX", ""):
            with self.subTest(value=value):
                self.assertIsNone(usps_state_code(value))

    def test_us_zip_formats(self):
        """Accept 5 digits or ZIP+4 for the USA and reject anything else."""
        for zip_code in ("97331", "97331-1234", ""):
            with self.subTest(zip_code=zip_code):
                self.assertEqual(clean_location("USA", "", zip_code)[2], {})
        for zip_code in ("9733", "973311", "97331-12", "97331 1234", "abcde", "٩٧٣٣١"):
            with self.subTest(zip_code=zip_code):
                self.assertEqual(clean_location("USA", "", zip_code)[2], {"ZIP": ZIP_MESSAGE})

    def test_other_countries_are_free_text(self):
        """Keep any State and postal code outside the USA."""
        self.assertEqual(
            clean_location("Canada", " Ontario ", "K1A 0B1"), ("Ontario", "K1A 0B1", {})
        )


class ZipStateFormTestBase(CompanyWorkflowHelpers, TestCase):
    """An editor and a published USA company."""

    def setUp(self):
        """Create the editor and the company."""
        self.editor = self._user("editor")
        self._grant(self.editor, EDIT_COMPANIES)
        self.submission = self._company_submission()
        self.company = Company.objects.create(
            SrcKey="",
            Name="Published company",
            Address="",
            State="OR",
            Country="USA",
            Status_id=self.submission["Status"],
            Industry_id=self.submission["Industry"],
            Grower_id=self.submission["Grower"],
        )
        patcher = patch("helloworld.views.email_admins")
        patcher.start()
        self.addCleanup(patcher.stop)
        # Keep edits that change location off the live geocoder
        patcher = patch("helloworld.views.geocode_location", return_value=(None, None))
        self.geocode = patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.editor)

    def _edit(self, **values):
        """Post an edit of the company and return the response."""
        data = {
            "SrcKey": "",
            "Name": self.company.Name,
            "Address": "",
            "Country": self.company.Country,
            "State": self.company.State,
            "Status": self.company.Status_id,
            "Industry": self.company.Industry_id,
            "Grower": self.company.Grower_id,
            "dateCreated": self.company.dateCreated.isoformat(),
            **values,
        }
        return self.client.post(reverse("edit-company", args=[self.company.pk]), data)

    def _pending(self):
        """Return the pending edit."""
        return PendingChanges.objects.get(company=self.company).pending_company


class EditFormTests(ZipStateFormTestBase):
    """The edit page validates State and ZIP by country."""

    def test_us_state_and_zip_go_to_pending_review(self):
        """Store a valid State code and ZIP+4 on the pending edit only."""
        response = self._edit(State="WA", ZIP="98101-1234")

        self.assertRedirects(response, "/companies", fetch_redirect_response=False)
        self.assertEqual((self._pending().State, self._pending().ZIP), ("WA", "98101-1234"))
        self.company.refresh_from_db()
        self.assertEqual((self.company.State, self.company.ZIP), ("OR", ""))

    def test_rejects_bad_us_state_and_zip(self):
        """Re-render with both errors and save nothing."""
        response = self._edit(State="Cascadia", ZIP="1234")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"State: {STATE_MESSAGE}")
        self.assertContains(response, f"ZIP code: {ZIP_MESSAGE}")
        self.assertFalse(PendingChanges.objects.exists())

    def test_rejects_full_state_name(self):
        """Require a USPS code on the edit page; only upload converts names."""
        response = self._edit(State="Washington")

        self.assertContains(response, f"State: {STATE_MESSAGE}")
        self.assertFalse(PendingChanges.objects.exists())

    def test_other_country_accepts_free_text(self):
        """Accept a province and postal code outside the USA."""
        self._edit(Country="Canada", State="Ontario", ZIP="K1A 0B1")

        self.assertEqual((self._pending().State, self._pending().ZIP), ("Ontario", "K1A 0B1"))

    def test_us_page_shows_enabled_dropdown(self):
        """Enable the USPS dropdown and disable the text box for a USA company."""
        response = self.client.get(reverse("edit-company", args=[self.company.pk]))

        self.assertContains(response, '<label for="id_State" class="form-label d-block mb-1">State</label>', html=True)
        self.assertContains(response, '<select name="State" class="form-select" id="id_State">')
        self.assertContains(response, '<option value="OR" selected>Oregon (OR)</option>', html=True)
        self.assertContains(response, 'disabled hidden>')

    def test_other_country_page_shows_enabled_text_box(self):
        """Disable the dropdown for a company outside the USA."""
        self.company.Country, self.company.State = "Canada", "Ontario"
        self.company.save()

        response = self.client.get(reverse("edit-company", args=[self.company.pk]))

        self.assertContains(response, '<select name="State" class="form-select" disabled hidden>')
        self.assertContains(response, 'value="Ontario" maxlength="250" id="id_State">')

    def test_unmapped_us_state_stays_selected(self):
        """Keep an unmapped value selected so the edit page can't blank it silently."""
        self.company.State = "Washington/Arizona"
        self.company.save()

        response = self.client.get(reverse("edit-company", args=[self.company.pk]))

        self.assertContains(
            response,
            '<option value="Washington/Arizona" selected data-unmapped>Washington/Arizona</option>',
            html=True,
        )

    def test_zip_change_needs_geocoding(self):
        """Count ZIP as a location field."""
        edited = PendingCompany(**self.company.shared_concrete_field_values(PendingCompany))
        edited.ZIP = "97331"

        self.assertTrue(check_if_location_edited(self.company, edited))


class CreateFormTests(ZipStateFormTestBase):
    """The create modal applies the same rules."""

    def test_rejects_bad_zip(self):
        """Show the error on the companies page and create nothing."""
        response = self.client.post(reverse("companies"), {**self.submission, "ZIP": "97"})

        self.assertContains(response, f"ZIP code: {ZIP_MESSAGE}")
        self.assertFalse(PendingCompany.objects.exists())

    def test_stores_state_code_and_zip(self):
        """Store the code and ZIP, and pass ZIP to the geocoder."""
        data = {**self.submission, "City": "Corvallis", "State": "OR", "ZIP": "97331"}

        self.client.post(reverse("companies"), data)

        pending = PendingCompany.objects.get()
        self.assertEqual((pending.State, pending.ZIP), ("OR", "97331"))
        self.geocode.assert_called_once_with("123 Main St", "Corvallis", "OR", "97331", "USA")


class CompanyOutputTests(ZipStateFormTestBase):
    """The company page and CSV export show ZIP."""

    def setUp(self):
        """Give the company a ZIP code."""
        super().setUp()
        self.company.ZIP = "97331-1234"
        self.company.save()

    def test_company_page_shows_zip(self):
        """List ZIP on the company page."""
        response = self.client.get(reverse("company-view", args=[self.company.pk]))

        self.assertContains(response, "97331-1234")

    def test_export_has_zip_column(self):
        """Write a ZIP column next to State."""
        response = self.client.get(reverse("export-companies"))

        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual((rows[0]["State"], rows[0]["ZIP"]), ("OR", "97331-1234"))


class ZipStateUploadTests(UploadTestBase):
    """Bulk upload converts State names and validates ZIP for USA rows."""

    def _upload(self, csv_rows):
        """Import a CSV with Country, State and ZIP columns."""
        refs = f"{self.status.pk},{self.industry.pk},{self.grower.pk}"
        lines = ["Name,Country,State,ZIP,Status,Industry,Grower"]
        lines += [f"Acme {index},{row},{refs}" for index, row in enumerate(csv_rows)]
        upload = StringIO("\n".join(lines) + "\n")
        return import_pending_companies(read_upload_dataframe(upload))

    def _stored(self):
        """Return staged (Country, State, ZIP) values in row order."""
        return list(PendingCompany.objects.order_by("pk").values_list("Country", "State", "ZIP"))

    def test_stores_codes_and_keeps_leading_zeros(self):
        """Store USPS codes for names or codes and keep ZIP as text."""
        self._upload(["USA,Massachusetts,02134", "US,ma,02134-0001", "Canada,Ontario,K1A 0B1", "USA,,"])

        self.assertEqual(
            self._stored(),
            [
                ("USA", "MA", "02134"),
                ("US", "MA", "02134-0001"),
                ("Canada", "Ontario", "K1A 0B1"),
                ("USA", "", ""),
            ],
        )

    def test_rejects_bad_us_values_naming_row_and_field(self):
        """Fail the whole upload with the row number and field name."""
        for row, field_name in (("USA,Cascadia,97331", "State"), ("USA,OR,9733", "ZIP")):
            with self.subTest(row=row):
                with self.assertRaises(UploadValidationError) as raised:
                    self._upload(["USA,OR,97331", row])

                self.assertIn(f"Row 3: {field_name} is invalid.", str(raised.exception))
                self.assertFalse(PendingCompany.objects.exists())

    def test_upload_without_zip_column_imports(self):
        """Import a frame with no State or ZIP column."""
        import_pending_companies(self._dataframe(1))

        self.assertEqual(self._stored(), [("USA", "", "")])

    def test_reads_zip_as_text_from_xlsx(self):
        """Keep a ZIP stored as text in a workbook."""
        refs = {"Status": self.status.pk, "Industry": self.industry.pk, "Grower": self.grower.pk}
        workbook = BytesIO()
        pd.DataFrame([{"Name": "Acme", "Country": "USA", "ZIP": "02134", **refs}]).to_excel(
            workbook, index=False
        )

        import_pending_companies(read_upload_dataframe(workbook))

        self.assertEqual(self._stored(), [("USA", "", "02134")])


class StateMigrationTests(TestCase):
    """The data migration converts US rows and reports what it can't map."""

    def _company(self, country, state, model=Company):
        """Create a bare company row."""
        return model.objects.create(SrcKey="", Name="Row", Address="", Country=country, State=state)

    def test_converts_us_and_placeholder_rows(self):
        """Store codes and Country USA, and leave other rows alone."""
        rows = {
            ("USA", "Florida"): ("USA", "FL"),
            ("United States", "OR"): ("USA", "OR"),
            ("--", "North Carolina"): ("USA", "NC"),
            ("1", "NC"): ("USA", "NC"),
            ("", "Washington, D.C."): ("USA", "DC"),
            ("USA", "Washington/Arizona"): ("USA", "Washington/Arizona"),
            ("--", "Ontario"): ("--", "Ontario"),
            ("--", ""): ("--", ""),
            ("Canada", "BC"): ("Canada", "BC"),
        }
        created = {key: self._company(*key) for key in rows}
        pending = self._company("--", "Oregon", model=PendingCompany)

        output = StringIO()
        with redirect_stdout(output):
            migration.convert_us_states(apps, None)

        for key, expected in rows.items():
            with self.subTest(row=key):
                created[key].refresh_from_db()
                self.assertEqual((created[key].Country, created[key].State), expected)
        pending.refresh_from_db()
        self.assertEqual((pending.Country, pending.State), ("USA", "OR"))
        self.assertIn("Company: converted 5 rows", output.getvalue())
        self.assertIn("'Washington/Arizona' (Country 'USA') on 1 rows", output.getvalue())
        self.assertIn("'Ontario' (Country '--') on 1 rows", output.getvalue())
