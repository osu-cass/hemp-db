"""Tests for filtering companies by State."""

import csv
from io import StringIO

from django.test import TestCase
from django.urls import reverse

from .forms import FilterStateForm
from .models import Company, Status
from .test_support import CompanyWorkflowHelpers


class StateFilterTests(CompanyWorkflowHelpers, TestCase):
    """The companies page and export filter by State."""

    def setUp(self):
        """Create companies in three states and one with no State."""
        self.active = Status.objects.create(status="Active")
        self.inactive = Status.objects.create(status="Inactive")
        for name, country, state, status in (
            ("Oregon Active", "USA", "OR", self.active),
            ("Oregon Inactive", "USA", "OR", self.inactive),
            ("Washington Active", "USA", "WA", self.active),
            ("Ontario Active", "Canada", "Ontario", self.active),
            ("No State", "USA", "", self.active),
        ):
            Company.objects.create(
                SrcKey="", Name=name, Address="", Country=country, State=state, Status=status
            )
        self.client.force_login(self._user("reader"))

    def _filter(self, **filters):
        """Post the filter modal and return the response."""
        return self.client.post(reverse("company-filtered"), {"item-filter": "", **filters})

    def _names(self, response):
        """Return which test companies the page lists."""
        return {
            company.Name
            for company in Company.objects.all()
            if f">{company.Name}<" in response.content.decode()
        }

    def test_lists_us_states_that_have_companies(self):
        """Offer each used USPS code once, by name, and leave out other countries' regions."""
        self.assertEqual(
            FilterStateForm().fields["state"].choices,
            [("OR", "Oregon (OR)"), ("WA", "Washington (WA)")],
        )

    def test_filters_by_one_or_more_states(self):
        """Show only companies in the selected states."""
        self.assertEqual(
            self._names(self._filter(state=["OR"])), {"Oregon Active", "Oregon Inactive"}
        )
        self.assertEqual(
            self._names(self._filter(state=["OR", "WA"])),
            {"Oregon Active", "Oregon Inactive", "Washington Active"},
        )

    def test_combines_with_other_filters(self):
        """Apply State and Status together."""
        response = self._filter(state=["OR"], status=[self.active.pk])

        self.assertEqual(self._names(response), {"Oregon Active"})

    def test_selected_states_stay_checked(self):
        """Keep the chosen states checked after the page reloads."""
        response = self._filter(state=["OR"])

        self.assertContains(response, '<option value="OR" selected>Oregon (OR)</option>')
        self.assertContains(response, '<option value="WA">Washington (WA)</option>')

    def test_export_applies_state_filter(self):
        """Export only the companies in the selected states."""
        response = self.client.post(reverse("export-companies"), {"state": ["WA"]})

        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual([row["Name"] for row in rows], ["Washington Active"])
