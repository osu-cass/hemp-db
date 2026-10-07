"""Validation and persistence helpers for staff company uploads."""

from __future__ import annotations

import re
import uuid
import zipfile

import pandas as pd
from django.db import transaction
from django.db.models import Exists, Min, OuterRef
from django.utils import timezone

from .models import Company, Grower, Industry, PendingCompany, Status, UploadIndex
from .signals import invalidate_map_cache


class UploadValidationError(ValueError):
    """Identify an upload that cannot be safely imported.

    ``errors`` holds every problem; the message may summarize them.
    """

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = list(errors) if errors else [message]


REQUIRED_UPLOAD_COLUMNS = frozenset({"Name", "Country", "Status", "Industry", "Grower"})
FOREIGN_KEY_MODELS = {
    "Status": Status,
    "Industry": Industry,
    "Grower": Grower,
}
EXCLUDED_MODEL_FIELDS = frozenset({"id", "dateCreated", "lastUpdated", "import_batch_id"})
IMPORT_BATCH_SIZE = 500
# Row problems listed in one error message; the rest are counted.
MAX_REPORTED_ROW_ERRORS = 10

SPREADSHEET_FIELDS = frozenset(
    field.name
    for field in PendingCompany._meta.concrete_fields
    if field.name not in EXCLUDED_MODEL_FIELDS
)
FIELD_MAX_LENGTHS = {
    field.name: field.max_length
    for field in PendingCompany._meta.concrete_fields
    if field.name in SPREADSHEET_FIELDS
    and field.max_length is not None
}


def _reset_file(uploaded_file):
    """Rewind an uploaded file before a parser reads it."""
    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError) as error:
        raise UploadValidationError("The uploaded file could not be read.") from error


def _is_xlsx(uploaded_file):
    """Return whether an uploaded file has the XLSX ZIP signature."""
    _reset_file(uploaded_file)
    signature = uploaded_file.read(4)
    _reset_file(uploaded_file)
    return signature == b"PK\x03\x04"


def _normalize_dataframe(dataframe):
    """Normalize spreadsheet headers and reject empty or duplicate headers."""
    if dataframe.empty:
        raise UploadValidationError("The uploaded file contains no data rows.")

    columns = [str(column).strip().lstrip("\ufeff") for column in dataframe.columns]
    if len(columns) != len(set(columns)):
        raise UploadValidationError("The uploaded file contains duplicate column names.")

    dataframe.columns = columns
    return dataframe


def _csv_parser_message(error):
    """Describe a CSV parse failure with pandas' line and reason."""
    summary = "The uploaded CSV has invalid row or delimiter formatting"
    detail = str(error).strip().removeprefix("Error tokenizing data. C error: ")
    if not detail:
        return f"{summary}."
    # pandas numbers this row from 0, with the header as row 0.
    detail = re.sub(
        r"EOF inside string starting at row (\d+)",
        lambda match: f"a quoted cell starting on line {int(match[1]) + 1} is never closed",
        detail,
    )
    note = (
        " Line numbers count the header as line 1 and a cell with line breaks as one line."
        if "line " in detail
        else ""
    )
    return f"{summary} ({detail}).{note}"


def read_upload_dataframe(uploaded_file):
    """Read a detectable XLSX workbook or a UTF-8 CSV upload."""
    if _is_xlsx(uploaded_file):
        _reset_file(uploaded_file)
        try:
            dataframe = pd.read_excel(uploaded_file, engine="openpyxl")
        except ImportError as error:
            raise UploadValidationError(
                "XLSX uploads require the openpyxl engine."
            ) from error
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            raise UploadValidationError("The XLSX workbook could not be read.") from error
    else:
        _reset_file(uploaded_file)
        try:
            dataframe = pd.read_csv(uploaded_file, encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise UploadValidationError(
                "CSV uploads must use UTF-8 encoding, including UTF-8 with a BOM."
            ) from error
        except pd.errors.EmptyDataError as error:
            raise UploadValidationError("The uploaded CSV contains no data.") from error
        except pd.errors.ParserError as error:
            raise UploadValidationError(_csv_parser_message(error)) from error

    return _normalize_dataframe(dataframe)


def validate_upload_columns(dataframe):
    """Ensure the upload contains the columns required by the import path."""
    missing_columns = sorted(REQUIRED_UPLOAD_COLUMNS - set(dataframe.columns))
    if missing_columns:
        columns = ", ".join(missing_columns)
        raise UploadValidationError(f"The upload is missing required columns: {columns}.")
    return dataframe


def _is_missing(value):
    """Return whether a scalar spreadsheet value is empty."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    missing = pd.isna(value)
    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False


def _base_record(row):
    """Map spreadsheet cells onto pending-company field names."""
    record = {}
    for field_name, value in row.items():
        if field_name not in SPREADSHEET_FIELDS:
            continue
        field = PendingCompany._meta.get_field(field_name)
        record[field_name] = (
            None if field.null else ""
        ) if _is_missing(value) else value
    for field_name in SPREADSHEET_FIELDS - record.keys():
        field = PendingCompany._meta.get_field(field_name)
        record[field_name] = None if field.null else ""
    return record


def _reference_id(value):
    """Coerce a spreadsheet cell into a whole-number primary key, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        as_float = float(value)
        # Reject fractional values rather than truncating toward zero.
        return int(as_float) if as_float.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def _reference_caches(records):
    """Prefetch each reference model once for the whole upload."""
    caches = {}
    for field_name, model in FOREIGN_KEY_MODELS.items():
        candidate_ids = {_reference_id(record.get(field_name)) for record in records}
        candidate_ids.discard(None)
        caches[field_name] = (
            model.objects.in_bulk(candidate_ids) if candidate_ids else {}
        )
    return caches


def _resolve_reference(field_name, model, value, row_number, references):
    """Substitute a referenced instance or raise an actionable row error."""
    if _is_missing(value):
        raise UploadValidationError(f"Row {row_number}: {field_name} is required.")

    instance = references.get(_reference_id(value))
    if instance is None:
        raise UploadValidationError(
            f"Row {row_number}: {field_name} must contain a valid {model.__name__} ID."
        )
    return instance


def _length_errors(record, row_number):
    """Return a row error for each value longer than its database column."""
    errors = []
    for field_name, max_length in FIELD_MAX_LENGTHS.items():
        value = record.get(field_name)
        if _is_missing(value):
            continue
        length = len(str(value))
        if length > max_length:
            errors.append(
                f"Row {row_number}: {field_name} is {length} characters; "
                f"the limit is {max_length}."
            )
    return errors


def _row_errors_message(errors):
    """Summarize row errors one per line, listing the first few and counting the rest."""
    if len(errors) == 1:
        return errors[0]
    lines = [
        f"{len(errors)} problems found. Correct these rows and upload again.",
        *errors[:MAX_REPORTED_ROW_ERRORS],
    ]
    remaining = len(errors) - MAX_REPORTED_ROW_ERRORS
    if remaining > 0:
        lines.append(f"And {remaining} more.")
    return "\n".join(lines)


def _validated_records(dataframe):
    """Validate every row and return constructor records in input order.

    Collects every row problem so one failed upload reports all of them.
    """
    rows = [
        (row_number, _base_record(row))
        for row_number, row in enumerate(dataframe.to_dict("records"), start=2)
    ]
    records = [record for _, record in rows]
    # A list, because _reference_caches iterates it once per reference model.
    caches = _reference_caches(records)
    required_columns = REQUIRED_UPLOAD_COLUMNS - FOREIGN_KEY_MODELS.keys()
    errors = []
    for row_number, record in rows:
        for field_name in sorted(required_columns):
            if _is_missing(record.get(field_name)):
                errors.append(f"Row {row_number}: {field_name} is required.")
        errors.extend(_length_errors(record, row_number))
        for field_name, model in FOREIGN_KEY_MODELS.items():
            try:
                record[field_name] = _resolve_reference(
                    field_name, model, record.get(field_name), row_number, caches[field_name]
                )
            except UploadValidationError as error:
                errors.append(str(error))
    if errors:
        raise UploadValidationError(_row_errors_message(errors), errors)
    return records


@transaction.atomic
def import_pending_companies(dataframe):
    """Validate and atomically create pending companies and upload indexes."""
    validate_upload_columns(dataframe)
    records = _validated_records(dataframe)
    batch_id = uuid.uuid4()
    staged = [PendingCompany(import_batch_id=batch_id, **record) for record in records]
    PendingCompany.objects.bulk_create(staged, batch_size=IMPORT_BATCH_SIZE)

    # MySQL cannot report generated ids from bulk_create; correlate rows by batch.
    persisted = list(PendingCompany.objects.filter(import_batch_id=batch_id).order_by("pk"))
    if len(persisted) != len(staged):
        raise RuntimeError("The number of staged rows did not match the uploaded rows.")

    UploadIndex.objects.bulk_create(
        (UploadIndex(pendingID=str(company.pk)) for company in persisted),
        batch_size=IMPORT_BATCH_SIZE,
    )
    PendingCompany.objects.filter(import_batch_id=batch_id).update(import_batch_id=None)
    for company in persisted:
        company.import_batch_id = None
    return persisted


def approve_pending_companies(*, unique_only: bool) -> int:
    """Promote indexed pending companies and remove the upload staging rows."""
    with transaction.atomic():
        pending_ids = list(
            UploadIndex.objects.select_for_update().values_list(
                "pendingID", flat=True
            )
        )
        if not pending_ids:
            return 0

        indexed_pending = PendingCompany.objects.filter(pk__in=pending_ids).order_by(
            "pk"
        )
        if unique_only:
            first_pending_ids = (
                indexed_pending.order_by()
                .values("Name")
                .annotate(first_pk=Min("pk"))
                .values("first_pk")
            )
            existing_company = Company.objects.filter(Name=OuterRef("Name"))
            pending = (
                indexed_pending.filter(pk__in=first_pending_ids)
                .annotate(company_exists=Exists(existing_company))
                .filter(company_exists=False)
            )
        else:
            pending = indexed_pending

        pending_companies = list(pending)
        approval_time = timezone.now()
        companies = [
            Company(
                **company.shared_concrete_field_values(
                    Company, excluded_fields={"lastUpdated"}
                ),
                lastUpdated=approval_time,
            )
            for company in pending_companies
        ]
        Company.objects.bulk_create(companies, batch_size=IMPORT_BATCH_SIZE)

        PendingCompany.objects.filter(pk__in=pending_ids).delete()
        UploadIndex.objects.all().delete()
        if companies:
            transaction.on_commit(lambda: invalidate_map_cache(sender=Company))
        return len(companies)
