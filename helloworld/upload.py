"""Validation and persistence helpers for staff company uploads."""

from __future__ import annotations

import zipfile

import pandas as pd
from django.db import transaction

from .models import Grower, Industry, PendingCompany, Status, UploadIndex


class UploadValidationError(ValueError):
    """Identify an upload that cannot be safely imported."""


REQUIRED_UPLOAD_COLUMNS = frozenset({"Name", "Country", "Status", "Industry", "Grower"})
FOREIGN_KEY_MODELS = {
    "Status": Status,
    "Industry": Industry,
    "Grower": Grower,
}
EXCLUDED_MODEL_FIELDS = frozenset({"id", "dateCreated", "lastUpdated"})


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
            raise UploadValidationError(
                "The uploaded CSV has invalid row or delimiter formatting."
            ) from error

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


def _foreign_key_value(field_name, value, row_number):
    """Resolve a foreign-key ID or raise an actionable row error."""
    if _is_missing(value):
        raise UploadValidationError(f"Row {row_number}: {field_name} is required.")

    model = FOREIGN_KEY_MODELS[field_name]
    try:
        return model.objects.get(pk=value)
    except (model.DoesNotExist, TypeError, ValueError) as error:
        raise UploadValidationError(
            f"Row {row_number}: {field_name} must contain a valid {model.__name__} ID."
        ) from error


def _pending_company_record(row, row_number):
    """Build one validated PendingCompany constructor record."""
    model_fields = {
        field.name
        for field in PendingCompany._meta.concrete_fields
        if field.name not in EXCLUDED_MODEL_FIELDS
    }
    record = {
        field_name: ("" if _is_missing(value) else value)
        for field_name, value in row.items()
        if field_name in model_fields
    }
    for field in PendingCompany._meta.concrete_fields:
        if field.name not in EXCLUDED_MODEL_FIELDS and field.name not in record:
            record[field.name] = None if field.null else ""

    for field_name in REQUIRED_UPLOAD_COLUMNS - FOREIGN_KEY_MODELS.keys():
        if _is_missing(record.get(field_name)):
            raise UploadValidationError(f"Row {row_number}: {field_name} is required.")

    for field_name in FOREIGN_KEY_MODELS:
        record[field_name] = _foreign_key_value(
            field_name, record.get(field_name), row_number
        )

    return record


@transaction.atomic
def import_pending_companies(dataframe):
    """Validate and atomically create pending companies and upload indexes."""
    validate_upload_columns(dataframe)
    created = []
    for row_number, row in enumerate(dataframe.to_dict("records"), start=2):
        company = PendingCompany(**_pending_company_record(row, row_number))
        company.save()
        UploadIndex.objects.create(pendingID=str(company.pk))
        created.append(company)
    return created
