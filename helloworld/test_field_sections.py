"""Tests for the grouped company form sections."""

from collections import Counter

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .forms import COMPANY_FIELD_SECTIONS, PendingCompanyForm
from .models import Company
from .permissions import EDIT_COMPANIES
from .test_support import CompanyWorkflowHelpers

TITLES = [title for title, _ in COMPANY_FIELD_SECTIONS]


class SectionListTests(SimpleTestCase):
    """The section list covers the form exactly."""

    def test_every_field_is_in_exactly_one_section(self):
        """Fail when a form field is missing, repeated or unknown."""
        listed = Counter(name for _, names in COMPANY_FIELD_SECTIONS for name in names)

        self.assertEqual([name for name, count in listed.items() if count > 1], [])
        self.assertEqual(set(listed), set(PendingCompanyForm.base_fields))


class SectionPageTests(CompanyWorkflowHelpers, TestCase):
    """The edit page and create modal show the same sections."""

    def setUp(self):
        """Create an editor and a company."""
        self.editor = self._user("editor")
        self._grant(self.editor, EDIT_COMPANIES)
        self.client.force_login(self.editor)
        self.company = Company.objects.create(SrcKey="", Name="Acme", Address="", Country="USA")

    def _assert_sections_in_order(self, response):
        """Check every legend appears once, in order."""
        content = response.content.decode()
        positions = [content.find(f'<legend class="h5 border-bottom pb-1">{title}</legend>') for title in TITLES]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))

    def test_edit_page(self):
        """Group the edit page fields."""
        self._assert_sections_in_order(
            self.client.get(reverse("edit-company", args=[self.company.pk]))
        )

    def test_create_modal(self):
        """Group the create modal fields."""
        self._assert_sections_in_order(self.client.get(reverse("companies")))
