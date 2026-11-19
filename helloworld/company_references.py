"""Company reference fields shared by forms, listings, uploads and exports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

# Company fields that hold several reference-table values.
MANY_TO_MANY_FIELDS = ("Category", "stakeholderGroup", "Stage", "productGroup", "Solutions")

# Filter form parameter for each filterable company field.
FILTER_PARAMETERS = {
    "Status": "status",
    "Industry": "industry",
    "Category": "category",
    "stakeholderGroup": "stakeholder_groups",
    "Stage": "stage",
    "productGroup": "product_group",
    "Solutions": "solution",
    "State": "state",
}

# Separates reference IDs within one spreadsheet cell.
ID_SEPARATOR = ";"

EMPTY_LABEL = "--"


def filter_companies(companies, data):
    """Apply the submitted filters to a company queryset.

    Args:
        companies: Company queryset to narrow.
        data: Submitted form data keyed by filter parameter.

    Returns:
        The filtered queryset with each company once, and the selected IDs per field.
    """
    selected = {
        field: data.getlist(parameter) for field, parameter in FILTER_PARAMETERS.items()
    }
    for field, ids in selected.items():
        if ids:
            companies = companies.filter(**{f"{field}__in": ids})
    return companies.distinct(), selected


def reference_labels(company) -> dict[str, str]:
    """Return each many-to-many field's values joined for display."""
    return {
        field: ", ".join(str(value) for value in getattr(company, field).all())
        or EMPTY_LABEL
        for field in MANY_TO_MANY_FIELDS
    }


def company_rows(companies) -> list[tuple]:
    """Pair each company with its display labels for the listing table."""
    return [(company, reference_labels(company)) for company in companies]


def reference_ids(company) -> dict[str, list[int]]:
    """Return the assigned IDs of each non-empty many-to-many field."""
    assigned = {
        field: sorted(value.pk for value in getattr(company, field).all())
        for field in MANY_TO_MANY_FIELDS
    }
    return {field: ids for field, ids in assigned.items() if ids}


def format_reference_ids(ids: Iterable[int]) -> str:
    """Join reference IDs into the spreadsheet cell format."""
    return ID_SEPARATOR.join(str(pk) for pk in ids)


def bulk_add_references(
    assignments: Iterable[tuple[object, Mapping[str, Iterable[int]]]], batch_size: int
) -> None:
    """Link saved companies to reference IDs with one insert per field.

    Args:
        assignments: Pairs of a saved company and its reference IDs by field name.
        batch_size: Maximum rows per insert statement.
    """
    rows = defaultdict(list)
    for company, references in assignments:
        for field_name, ids in references.items():
            field = type(company)._meta.get_field(field_name)
            through = field.remote_field.through
            source = f"{field.m2m_field_name()}_id"
            target = f"{field.m2m_reverse_field_name()}_id"
            rows[through].extend(
                through(**{source: company.pk, target: pk}) for pk in ids
            )
    for through, links in rows.items():
        through.objects.bulk_create(links, batch_size=batch_size)
