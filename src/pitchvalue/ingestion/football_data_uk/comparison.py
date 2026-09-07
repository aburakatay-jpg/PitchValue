"""Deterministic, non-mutating comparison of football-data-style CSV bytes."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Literal

from pitchvalue.ingestion.football_data_uk.parser import ParsedDataset, ParsedRow, parse_csv
from pitchvalue.ingestion.football_data_uk.raw import sha256_bytes

ComparisonStatus = Literal[
    "EXACT_MATCH", "SEMANTIC_MATCH_BYTE_DIFFERENCE", "DATA_DIFFERENCE", "AMBIGUOUS"
]


@dataclass(frozen=True)
class ArtifactComparison:
    status: ComparisonStatus
    sha256_a: str
    sha256_b: str
    row_count_a: int
    row_count_b: int
    columns_a: tuple[str, ...]
    columns_b: tuple[str, ...]
    columns_only_a: tuple[str, ...]
    columns_only_b: tuple[str, ...]
    key_fields: tuple[str, ...]
    core_match_key_row_count_a: int
    core_match_key_row_count_b: int
    rows_only_a: int
    rows_only_b: int
    differing_matching_rows: int
    ambiguous_keys_a: int
    ambiguous_keys_b: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _use_time(a: ParsedDataset, b: ParsedDataset) -> bool:
    return (
        "Time" in a.columns
        and "Time" in b.columns
        and all(row.normalized_values.get("Time") is not None for row in (*a.rows, *b.rows))
    )


def _key(row: ParsedRow, fields: tuple[str, ...]) -> tuple[str, ...] | None:
    values = tuple(row.normalized_values.get(field) for field in fields)
    if any(value is None for value in values):
        return None
    return tuple(value for value in values if value is not None)


def _indexed(
    dataset: ParsedDataset, fields: tuple[str, ...]
) -> tuple[dict[tuple[str, ...], ParsedRow], int, int]:
    keyed = [(key, row) for row in dataset.rows if (key := _key(row, fields)) is not None]
    counts = Counter(key for key, _ in keyed)
    ambiguous = {key for key, count in counts.items() if count > 1}
    unique = {key: row for key, row in keyed if key not in ambiguous}
    return unique, len(keyed), len(ambiguous)


def compare_artifacts(content_a: bytes, content_b: bytes) -> ArtifactComparison:
    """Compare hashes, schemas, conservative match keys, and matching row values."""
    dataset_a = parse_csv(content_a)
    dataset_b = parse_csv(content_b)
    base_fields = ("Div", "Date", "HomeTeam", "AwayTeam")
    key_fields = (*base_fields, "Time") if _use_time(dataset_a, dataset_b) else base_fields
    indexed_a, keyed_a, ambiguous_a = _indexed(dataset_a, key_fields)
    indexed_b, keyed_b, ambiguous_b = _indexed(dataset_b, key_fields)
    keys_a = set(indexed_a)
    keys_b = set(indexed_b)
    common_columns = set(dataset_a.columns).intersection(dataset_b.columns)
    differing = sum(
        any(
            indexed_a[key].raw_values.get(column) != indexed_b[key].raw_values.get(column)
            for column in common_columns
        )
        for key in keys_a.intersection(keys_b)
    )
    hash_a = sha256_bytes(content_a)
    hash_b = sha256_bytes(content_b)
    rows_only_a = len(keys_a - keys_b)
    rows_only_b = len(keys_b - keys_a)
    if hash_a == hash_b:
        status: ComparisonStatus = "EXACT_MATCH"
    elif ambiguous_a or ambiguous_b:
        status = "AMBIGUOUS"
    elif rows_only_a or rows_only_b or differing:
        status = "DATA_DIFFERENCE"
    else:
        status = "SEMANTIC_MATCH_BYTE_DIFFERENCE"
    return ArtifactComparison(
        status=status,
        sha256_a=hash_a,
        sha256_b=hash_b,
        row_count_a=len(dataset_a.rows),
        row_count_b=len(dataset_b.rows),
        columns_a=dataset_a.columns,
        columns_b=dataset_b.columns,
        columns_only_a=tuple(sorted(set(dataset_a.columns) - set(dataset_b.columns))),
        columns_only_b=tuple(sorted(set(dataset_b.columns) - set(dataset_a.columns))),
        key_fields=key_fields,
        core_match_key_row_count_a=keyed_a,
        core_match_key_row_count_b=keyed_b,
        rows_only_a=rows_only_a,
        rows_only_b=rows_only_b,
        differing_matching_rows=differing,
        ambiguous_keys_a=ambiguous_a,
        ambiguous_keys_b=ambiguous_b,
    )
