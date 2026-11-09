"""Queries and keyset pages for progressively loaded pending changes."""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import Count, Max, Min, Q
from django.utils.dateparse import parse_datetime

from .models import PendingChanges


PAGE_SIZE = 100


@dataclass(frozen=True)
class PendingCategory:
    """Describe how a pending-change category relates to a company."""

    change_type: str
    company_relation: str

    @property
    def company_id_field(self) -> str:
        """Return the foreign-key column for this category's company."""
        return f"{self.company_relation}_id"


CATEGORIES = {
    "edit": PendingCategory("edit", "company"),
    "create": PendingCategory("create", "pending_company"),
    "delete": PendingCategory("deletion", "company"),
}


@dataclass(frozen=True)
class CompanySummary:
    """Summarize a company with pending changes."""

    company_id: int
    company_name: str
    pending_count: int


@dataclass(frozen=True)
class PendingPage:
    """Hold one bounded result page and its next cursor."""

    items: list
    next_cursor: str | None


def get_category(category: str) -> PendingCategory:
    """Return the query configuration for a public category name."""
    config = CATEGORIES.get(category)
    if config is None:
        raise ValueError("Unknown pending-change category.")
    return config


def get_category_counts() -> dict[str, int]:
    """Count companies with pending changes in each category."""
    return PendingChanges.objects.filter(
        status=PendingChanges.PendingStatus.PENDING
    ).aggregate(
        **{
            name: Count(
                config.company_id_field,
                filter=Q(changeType=config.change_type),
                distinct=True,
            )
            for name, config in CATEGORIES.items()
        }
    )


def get_upload_batches():
    """Summarize upload batches that still have pending creates."""
    return (
        PendingChanges.objects.filter(
            changeType=CATEGORIES["create"].change_type,
            status=PendingChanges.PendingStatus.PENDING,
            upload_batch__isnull=False,
        )
        .values("upload_batch", "author__username")
        .annotate(company_count=Count("pk"), submitted_at=Min("created_at"))
        .order_by("-submitted_at")
    )


def get_company_page(
    category: str,
    cursor: str | None = None,
    page_size: int = PAGE_SIZE,
) -> PendingPage:
    """Return one page of company summaries, newest pending change first."""
    config = get_category(category)
    id_field = config.company_id_field
    name_field = f"{config.company_relation}__Name"
    queryset = (
        PendingChanges.objects.filter(
            changeType=config.change_type,
            status=PendingChanges.PendingStatus.PENDING,
            **{f"{id_field}__isnull": False},
        )
        .values(id_field, name_field)
        .annotate(pending_count=Count("id"), newest_change_at=Max("created_at"))
    )
    rows = list(
        _after_cursor(queryset, cursor, "newest_change_at", id_field)
        .order_by("-newest_change_at", f"-{id_field}")[: page_size + 1]
    )
    rows, next_cursor = _split_page(
        rows, page_size, lambda row: (row["newest_change_at"], row[id_field])
    )
    summaries = [
        CompanySummary(row[id_field], row[name_field], row["pending_count"])
        for row in rows
    ]
    return PendingPage(summaries, next_cursor)


def get_change_page(
    category: str,
    company_id: int,
    cursor: str | None = None,
    page_size: int = PAGE_SIZE,
) -> PendingPage:
    """Return one page of a company's pending changes, newest first."""
    config = get_category(category)
    queryset = PendingChanges.objects.filter(
        changeType=config.change_type,
        status=PendingChanges.PendingStatus.PENDING,
        **{config.company_id_field: company_id},
    )
    changes = list(
        _after_cursor(queryset, cursor, "created_at", "id")
        .select_related("author")
        .only("id", "changeType", "created_at", "author_id", "author__username")
        .order_by("-created_at", "-id")[: page_size + 1]
    )
    changes, next_cursor = _split_page(
        changes, page_size, lambda change: (change.created_at, change.id)
    )
    return PendingPage(changes, next_cursor)


def _after_cursor(queryset, cursor: str | None, time_field: str, id_field: str):
    """Keep rows that sort after the cursor in (time, id) descending order."""
    if not cursor:
        return queryset
    timestamp, row_id = _decode_cursor(cursor)
    return queryset.filter(
        Q(**{f"{time_field}__lt": timestamp})
        | Q(**{time_field: timestamp, f"{id_field}__lt": row_id})
    )


def _split_page(rows: list, page_size: int, cursor_key) -> tuple[list, str | None]:
    """Drop the look-ahead row and build the next cursor when one exists."""
    if len(rows) <= page_size:
        return rows, None
    rows = rows[:page_size]
    timestamp, row_id = cursor_key(rows[-1])
    return rows, f"{timestamp.isoformat()}_{row_id}"


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Parse a ``<iso timestamp>_<id>`` cursor or raise ValueError."""
    timestamp, _, row_id = cursor.rpartition("_")
    parsed = parse_datetime(timestamp)
    if parsed is None or parsed.tzinfo is None or not row_id.isdecimal():
        raise ValueError("Invalid pending-change cursor.")
    return parsed, int(row_id)
