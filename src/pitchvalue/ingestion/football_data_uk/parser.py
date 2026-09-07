"""Deterministic CSV and scalar parsing without canonical transformation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

CORE_COLUMNS = ("Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR")
INTEGER_COLUMNS = frozenset(
    {
        "FTHG",
        "FTAG",
        "HTHG",
        "HTAG",
        "HS",
        "AS",
        "HST",
        "AST",
        "HC",
        "AC",
        "HF",
        "AF",
        "HY",
        "AY",
        "HR",
        "AR",
    }
)
DECIMAL_COLUMNS = frozenset({"B365H", "B365D", "B365A"})
logger = logging.getLogger(__name__)


class ParseError(ValueError):
    """Raised for explicit non-blank scalar parsing failures."""


def normalize_blank(value: str | None) -> str | None:
    """Normalize blank/whitespace source cells to missing while preserving text."""
    if value is None or not value.strip():
        return None
    return value.strip()


def parse_nullable_int(value: str | None) -> int | None:
    """Parse an integer while distinguishing blank from numeric zero."""
    normalized = normalize_blank(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except ValueError as error:
        raise ParseError(f"invalid integer: {value!r}") from error


def parse_nullable_decimal(value: str | None) -> Decimal | None:
    """Parse an exact decimal while preserving missing values."""
    normalized = normalize_blank(value)
    if normalized is None:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation as error:
        raise ParseError(f"invalid decimal: {value!r}") from error


def parse_source_date(value: str | None) -> date | None:
    """Parse only explicit day-first provider date formats."""
    normalized = normalize_blank(value)
    if normalized is None:
        return None
    for format_string in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(normalized, format_string).date()
        except ValueError:
            continue
    raise ParseError(f"invalid date: {value!r}")


def parse_source_time(value: str | None) -> time | None:
    """Parse an optional 24-hour time without fabricating a missing time."""
    normalized = normalize_blank(value)
    if normalized is None:
        return None
    try:
        hour, minute = (int(part) for part in normalized.split(":"))
        return time(hour, minute)
    except (ValueError, TypeError) as error:
        raise ParseError(f"invalid time: {value!r}") from error


RawValue = str | list[str] | None


@dataclass(frozen=True)
class ParsedRow:
    """One preserved provider row and its deterministic validation result."""

    source_row_number: int
    raw_values: dict[str, RawValue]
    normalized_values: dict[str, str | None]
    row_hash: str
    errors: tuple[str, ...]

    @property
    def parsing_status(self) -> str:
        return "rejected" if self.errors else "parsed"


@dataclass(frozen=True)
class ParsedDataset:
    """Parsed CSV headers and rows, including rejected evidence."""

    columns: tuple[str, ...]
    rows: tuple[ParsedRow, ...]


def _row_hash(raw_values: dict[str, RawValue]) -> str:
    serialized = json.dumps(
        raw_values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def parse_csv(content: bytes) -> ParsedDataset:
    """Parse original CSV bytes while retaining every source column and row."""
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ParseError("source is not valid UTF-8") from error
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if reader.fieldnames is None:
        raise ParseError("CSV header is missing")
    columns = tuple(reader.fieldnames)
    rows: list[ParsedRow] = []
    for row_number, source_row in enumerate(reader, start=2):
        if all(
            value is None or (isinstance(value, str) and normalize_blank(value) is None)
            for value in source_row.values()
        ):
            continue
        raw_values: dict[str, RawValue] = {
            ("__extra_values__" if key is None else key): value for key, value in source_row.items()
        }
        normalized = {
            key: normalize_blank(value)
            for key, value in source_row.items()
            if key is not None and isinstance(value, (str, type(None)))
        }
        errors: list[str] = []
        if None in source_row:
            errors.append("row has more values than the header")
        for column in CORE_COLUMNS:
            if column not in columns:
                errors.append(f"{column}: required column is missing")
                continue
            if normalized.get(column) is None:
                errors.append(f"{column}: required value is missing")
        if "Date" in columns and normalized.get("Date") is not None:
            try:
                parse_source_date(normalized["Date"])
            except ParseError as error:
                errors.append(f"Date: {error}")
        if "Time" in columns and normalized.get("Time") is not None:
            try:
                parse_source_time(normalized["Time"])
            except ParseError as error:
                errors.append(f"Time: {error}")
        for column in INTEGER_COLUMNS.intersection(columns):
            try:
                parse_nullable_int(normalized[column])
            except ParseError as error:
                errors.append(f"{column}: {error}")
        for column in DECIMAL_COLUMNS.intersection(columns):
            try:
                parse_nullable_decimal(normalized[column])
            except ParseError as error:
                errors.append(f"{column}: {error}")
        if errors:
            logger.warning("parse errors on source row %s: %s", row_number, "; ".join(errors))
        rows.append(
            ParsedRow(
                source_row_number=row_number,
                raw_values=raw_values,
                normalized_values=normalized,
                row_hash=_row_hash(raw_values),
                errors=tuple(errors),
            )
        )
    return ParsedDataset(columns, tuple(rows))
