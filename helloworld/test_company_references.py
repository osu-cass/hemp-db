"""Tests for multi-value company reference fields."""

import csv
import io

import pandas as pd
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from .company_references import reference_labels
from .forms import PendingCompanyForm
from .models import (
    Category,
    Company,
    Grower,
    Industry,
    PendingChanges,
    PendingCompany,
    Stage,
    Status,
    stakeholderGroups,
)
from .permissions import EDIT_COMPANIES
from .upload import (
    UploadValidationError,
    approve_upload_batch,
    import_pending_companies,
    submit_upload_for_review,
)


class ReferenceDataMixin:
    """Create reference rows and a company with two categories."""

    def setUp(self):
        """Create shared reference rows."""
        self.status = Status.objects.create(status="Active")
        self.industry = Industry.objects.create(industry="Hemp")
        self.grower = Grower.objects.create(grower="Grower")
        self.grower_category = Category.objects.create(category="Grower")
        self.processor = Category.objects.create(category="Processor")
        self.retailer = Category.objects.create(category="Retailer")
        self.farmers = stakeholderGroups.objects.create(stakeholderGroup="Farmers", category=1)
        self.startup = Stage.objects.create(stage="Startup")

    def _company(self, name, categories=()):
        """Create a published company with the given categories."""
        company = Company.objects.create(
            SrcKey="", Name=name, Address="", Country="USA", Status=self.status
        )
        company.Category.set(categories)
        return company

    def _form_data(self, **values):
        """Return valid company form data with extra values."""
        data = {
            "SrcKey": "",
            "Name": "Acme",
            "Address": "",
            "Country": "USA",
            "dateCreated": "2026-01-01 00:00",
            "Status": self.status.pk,
            "Industry": self.industry.pk,
            "Grower": self.grower.pk,
        }
        data.update(values)
        return data

    def _dataframe(self, **columns):
        """Build a one-row upload frame with extra columns."""
        row = {
            "Name": "Upload Co",
            "Country": "USA",
            "Status": self.status.pk,
            "Industry": self.industry.pk,
            "Grower": self.grower.pk,
        }
        row.update(columns)
        return pd.DataFrame([row])


class CompanyFormTests(ReferenceDataMixin, TestCase):
    """Verify company forms offer checkboxes for categories and stakeholder groups."""

    def test_category_fields_render_as_checkboxes(self):
        """Render Category and stakeholderGroup as checkbox lists, the rest unchanged."""
        form = PendingCompanyForm()

        for field_name in ("Category", "stakeholderGroup"):
            with self.subTest(field=field_name):
                self.assertIsInstance(
                    form.fields[field_name].widget, forms.CheckboxSelectMultiple
                )
        for field_name in ("Stage", "productGroup", "Solutions"):
            with self.subTest(field=field_name):
                self.assertNotIsInstance(
                    form.fields[field_name].widget, forms.CheckboxSelectMultiple
                )
        self.assertIn('type="checkbox"', str(form["Category"]))

    def test_form_saves_several_categories(self):
        """Keep every ticked category when the form saves."""
        form = PendingCompanyForm(
            self._form_data(Category=[self.grower_category.pk, self.processor.pk])
        )

        self.assertTrue(form.is_valid(), form.errors)
        company = form.save()

        self.assertCountEqual(
            company.Category.values_list("pk", flat=True),
            [self.grower_category.pk, self.processor.pk],
        )


class CompanyListingTests(ReferenceDataMixin, TestCase):
    """Verify listings show every value and each company once."""

    def setUp(self):
        """Sign in a reader."""
        super().setUp()
        self.client.force_login(
            get_user_model().objects.create_user(username="reader", password="password")
        )

    def test_labels_join_every_value_or_show_placeholder(self):
        """Join several values with commas and show a dash pair when empty."""
        company = self._company("Acme", [self.grower_category, self.processor])

        labels = reference_labels(company)

        self.assertEqual(labels["Category"], "Grower, Processor")
        self.assertEqual(labels["Stage"], "--")

    def test_list_page_shows_every_category(self):
        """Show all of a company's categories in the listing table."""
        self._company("Acme", [self.grower_category, self.processor])

        response = self.client.get(reverse("companies"))

        self.assertContains(response, "Grower, Processor")

    def test_filter_lists_company_once_when_it_matches_several_values(self):
        """Return one row for a company matching two selected categories."""
        self._company("Acme", [self.grower_category, self.processor])
        self._company("Other", [self.retailer])

        response = self.client.post(
            reverse("company-filtered"),
            {
                "item-filter": "",
                "category": [self.grower_category.pk, self.processor.pk],
            },
        )

        names = [company.Name for company, _ in response.context["companies"]]
        self.assertEqual(names, ["Acme"])


class CompanyExportTests(ReferenceDataMixin, TestCase):
    """Verify the CSV export writes reference IDs in the upload format."""

    def setUp(self):
        """Sign in a reader."""
        super().setUp()
        self.client.force_login(
            get_user_model().objects.create_user(username="reader", password="password")
        )

    def _rows(self, response):
        """Parse an export response into dictionaries."""
        return list(csv.DictReader(io.StringIO(response.content.decode())))

    def test_export_writes_semicolon_separated_ids(self):
        """Write each many-to-many column as sorted IDs joined by semicolons."""
        company = self._company("Acme", [self.processor, self.grower_category])
        company.stakeholderGroup.set([self.farmers])

        rows = self._rows(self.client.get(reverse("export-companies")))

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["Category"], f"{self.grower_category.pk};{self.processor.pk}"
        )
        self.assertEqual(rows[0]["stakeholderGroup"], str(self.farmers.pk))
        self.assertEqual(rows[0]["Stage"], "")
        self.assertEqual(rows[0]["Status"], str(self.status.pk))

    def test_filtered_export_lists_company_once(self):
        """Export one row for a company matching two selected categories."""
        self._company("Acme", [self.grower_category, self.processor])

        response = self.client.post(
            reverse("export-companies"),
            {"category": [self.grower_category.pk, self.processor.pk]},
        )

        self.assertEqual([row["Name"] for row in self._rows(response)], ["Acme"])


class ReferenceUploadTests(ReferenceDataMixin, TestCase):
    """Verify uploads read and publish semicolon-separated reference IDs."""

    def test_upload_assigns_every_listed_id(self):
        """Link a staged company to each ID in the cell."""
        cell = f"{self.grower_category.pk}; {self.processor.pk}"

        company = import_pending_companies(self._dataframe(Category=cell))[0]

        self.assertCountEqual(
            company.Category.values_list("pk", flat=True),
            [self.grower_category.pk, self.processor.pk],
        )

    def test_upload_reads_single_numeric_id(self):
        """Accept a lone numeric ID read by pandas as a number."""
        company = import_pending_companies(self._dataframe(Stage=float(self.startup.pk)))[0]

        self.assertEqual(list(company.Stage.all()), [self.startup])

    def test_blank_cell_assigns_nothing(self):
        """Leave the field empty when the cell is blank."""
        company = import_pending_companies(self._dataframe(Category=""))[0]

        self.assertFalse(company.Category.exists())

    def test_unknown_id_names_row_and_column(self):
        """Reject an ID that does not exist and stage nothing."""
        with self.assertRaisesMessage(
            UploadValidationError, "Row 2: Category ID 999999 does not exist."
        ):
            import_pending_companies(
                self._dataframe(Category=f"{self.processor.pk};999999")
            )

        self.assertFalse(PendingCompany.objects.exists())

    def test_malformed_id_names_row_and_column(self):
        """Reject a cell that is not a list of whole-number IDs."""
        with self.assertRaisesMessage(
            UploadValidationError,
            "Row 2: stakeholderGroup must contain IDs separated by semicolons.",
        ):
            import_pending_companies(self._dataframe(stakeholderGroup="Farmers"))

    def test_approval_copies_references_to_published_companies(self):
        """Publish linked and unlinked rows of one upload with their categories."""
        dataframe = pd.concat(
            [
                self._dataframe(Name="Linked", Category=str(self.processor.pk)),
                self._dataframe(Name="Plain", Category=""),
            ],
            ignore_index=True,
        )
        import_pending_companies(dataframe)
        author = get_user_model().objects.create_user(username="uploader", password="password")
        submit_upload_for_review(author, unique_only=False)
        batch = PendingChanges.objects.latest("pk").upload_batch

        with self.captureOnCommitCallbacks(execute=True):
            approved = approve_upload_batch(batch)

        self.assertEqual(approved, 2)
        self.assertEqual(
            list(Company.objects.get(Name="Linked").Category.all()), [self.processor]
        )
        self.assertFalse(Company.objects.get(Name="Plain").Category.exists())


class EditSubmissionTests(ReferenceDataMixin, TestCase):
    """Verify an edit keeps every ticked value."""

    def test_edit_submits_several_categories(self):
        """Stage an edit with two categories from the checkbox list."""
        editor = get_user_model().objects.create_user(username="editor", password="password")
        editor.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Company),
                codename=EDIT_COMPANIES.rsplit(".", 1)[1],
            )
        )
        self.client.force_login(editor)
        company = self._company("Acme", [self.retailer])

        self.client.post(
            reverse("edit-company", args=[company.pk]),
            self._form_data(Category=[self.grower_category.pk, self.processor.pk]),
        )

        pending = PendingChanges.objects.get(company=company).pending_company
        self.assertCountEqual(
            pending.Category.values_list("pk", flat=True),
            [self.grower_category.pk, self.processor.pk],
        )
