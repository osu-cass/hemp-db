"""Queries and cursors for progressively loaded pending changes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from django.core import signing
from django.db.models import Count, Max, Q
from django.utils.dateparse import parse_datetime

from .models import PendingChanges


PAGE_SIZE = 100
_CURSOR_SALT = "helloworld.pending-changes"


@dataclass(frozen=True)
class PendingCategory:
    """Describe how a pending-change category relates to a company."""

    change_type: str
    company_relation: str


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


Item = TypeVar("Item")


@dataclass(frozen=True)
class PendingPage(Generic[Item]):
    """Hold one bounded result page and its next cursor."""

    items: list[Item]
    next_cursor: str | None


class InvalidCursor(ValueError):
    """Indicate that a pending-change cursor cannot be used."""


def get_category(category: str) -> PendingCategory:
    """Return the query configuration for a public category name."""
    config = CATEGORIES.get(category)
    if config is None:
        raise ValueError("Unknown pending-change category.")
    return config


def get_category_counts() -> dict[str, int]:
    """Count companies with pending changes in each category."""
    pending = PendingChanges.objects.filter(
        status=PendingChanges.PendingStatus.PENDING
    )
    return pending.aggregate(
        edit=Count(
            "company_id",
            filter=Q(changeType=CATEGORIES["edit"].change_type),
            distinct=True,
        ),
        create=Count(
            "pending_company_id",
            filter=Q(changeType=CATEGORIES["create"].change_type),
            distinct=True,
        ),
        delete=Count(
            "company_id",
            filter=Q(changeType=CATEGORIES["delete"].change_type),
            distinct=True,
        ),
    )


def get_company_page(
    category: str,
    cursor: str | None = None,
    page_size: int = PAGE_SIZE,
) -> PendingPage[CompanySummary]:
    """Return one ordered page of company summaries."""
    config = get_category(category)
    relation_id = f"{config.company_relation}_id"
    relation_name = f"{config.company_relation}__Name"
    queryset = PendingChanges.objects.filter(
        changeType=config.change_type,
        status=PendingChanges.PendingStatus.PENDING,
        **{f"{relation_id}__isnull": False},
    )
    cursor_data = _decode_cursor(cursor, "companies", category) if cursor else None

    if category == "create":
        queryset = queryset.values(relation_id, relation_name).annotate(
            pending_count=Count("id"),
            newest_change_at=Max("created_at"),
        )
        if cursor_data:
            created_at = _parse_cursor_datetime(cursor_data, "created_at")
            company_id = _parse_cursor_int(cursor_data, "company_id")
            queryset = queryset.filter(
                Q(newest_change_at__lt=created_at)
                | Q(newest_change_at=created_at, pending_company_id__gt=company_id)
            )
        queryset = queryset.order_by("-newest_change_at", relation_id)
    else:
        if cursor_data:
            queryset = queryset.filter(
                **{f"{relation_id}__gt": _parse_cursor_int(cursor_data, "company_id")}
            )
        queryset = (
            queryset.values(relation_id, relation_name)
            .annotate(pending_count=Count("id"))
            .order_by(relation_id)
        )

    rows = list(queryset[: page_size + 1])
    page_rows = rows[:page_size]
    summaries = [
        CompanySummary(
            company_id=row[relation_id],
            company_name=row[relation_name],
            pending_count=row["pending_count"],
        )
        for row in page_rows
    ]
    next_cursor = None
    if len(rows) > page_size:
        last_row = page_rows[-1]
        cursor_values = {"company_id": last_row[relation_id]}
        if category == "create":
            cursor_values["created_at"] = last_row["newest_change_at"].isoformat()
        next_cursor = _encode_cursor("companies", category, cursor_values)

    return PendingPage(summaries, next_cursor)


def get_change_page(
    category: str,
    company_id: int,
    cursor: str | None = None,
    page_size: int = PAGE_SIZE,
) -> PendingPage[PendingChanges]:
    """Return one ordered page of pending changes for a company."""
    config = get_category(category)
    relation_id = f"{config.company_relation}_id"
    queryset = PendingChanges.objects.filter(
        changeType=config.change_type,
        status=PendingChanges.PendingStatus.PENDING,
        **{relation_id: company_id},
    )
    if cursor:
        cursor_data = _decode_cursor(cursor, "changes", category, company_id)
        created_at = _parse_cursor_datetime(cursor_data, "created_at")
        change_id = _parse_cursor_int(cursor_data, "change_id")
        queryset = queryset.filter(
            Q(created_at__lt=created_at)
            | Q(created_at=created_at, id__lt=change_id)
        )

    changes = list(
        queryset.select_related("author")
        .only("id", "changeType", "created_at", "author_id", "author__username")
        .order_by("-created_at", "-id")[: page_size + 1]
    )
    page_changes = changes[:page_size]
    next_cursor = None
    if len(changes) > page_size:
        last_change = page_changes[-1]
        next_cursor = _encode_cursor(
            "changes",
            category,
            {
                "company_id": company_id,
                "created_at": last_change.created_at.isoformat(),
                "change_id": last_change.id,
            },
        )

    return PendingPage(page_changes, next_cursor)


def _encode_cursor(kind: str, category: str, values: dict) -> str:
    """Sign cursor values for a specific result set."""
    return signing.dumps(
        {"kind": kind, "category": category, **values},
        salt=_CURSOR_SALT,
        compress=True,
    )


def _decode_cursor(
    cursor: str,
    kind: str,
    category: str,
    company_id: int | None = None,
) -> dict:
    """Validate and decode a cursor for a specific result set."""
    try:
        data = signing.loads(cursor, salt=_CURSOR_SALT)
    except (signing.BadSignature, TypeError) as error:
        raise InvalidCursor("Invalid pending-change cursor.") from error

    if not isinstance(data, dict):
        raise InvalidCursor("Invalid pending-change cursor.")
    if data.get("kind") != kind or data.get("category") != category:
        raise InvalidCursor("Cursor does not match this result set.")
    if company_id is not None and data.get("company_id") != company_id:
        raise InvalidCursor("Cursor does not match this company.")
    return data


def _parse_cursor_int(data: dict, key: str) -> int:
    """Read a positive integer from decoded cursor data."""
    value = data.get(key)
    if not isinstance(value, int) or value < 1:
        raise InvalidCursor("Invalid pending-change cursor.")
    return value


def _parse_cursor_datetime(data: dict, key: str) -> datetime:
    """Read an aware datetime from decoded cursor data."""
    value = data.get(key)
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is None or parsed.tzinfo is None:
        raise InvalidCursor("Invalid pending-change cursor.")
    return parsed
