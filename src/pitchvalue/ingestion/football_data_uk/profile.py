"""Source schema and validation profiling."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from pitchvalue.ingestion.football_data_uk.parser import (
    CORE_COLUMNS,
    DECIMAL_COLUMNS,
    INTEGER_COLUMNS,
    ParsedDataset,
)


@dataclass(frozen=True)
class SourceProfile:
    """Serializable profile of one parsed provider CSV."""

    row_count: int
    column_names: tuple[str, ...]
    missingness: dict[str, int]
    duplicate_raw_row_hashes: int
    malformed_rows: int
    date_parse_failures: int
    numeric_parse_failures: int
    core_column_availability: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable report."""
        return asdict(self)


def profile_dataset(dataset: ParsedDataset) -> SourceProfile:
    """Compute structural, missingness, duplicate, and parse-failure metrics."""
    hash_counts = Counter(row.row_hash for row in dataset.rows)
    return SourceProfile(
        row_count=len(dataset.rows),
        column_names=dataset.columns,
        missingness={
            column: sum(row.normalized_values.get(column) is None for row in dataset.rows)
            for column in dataset.columns
        },
        duplicate_raw_row_hashes=sum(count - 1 for count in hash_counts.values() if count > 1),
        malformed_rows=sum(bool(row.errors) for row in dataset.rows),
        date_parse_failures=sum(
            any(error.startswith("Date:") for error in row.errors) for row in dataset.rows
        ),
        numeric_parse_failures=sum(
            sum(error.split(":", 1)[0] in INTEGER_COLUMNS | DECIMAL_COLUMNS for error in row.errors)
            for row in dataset.rows
        ),
        core_column_availability={column: column in dataset.columns for column in CORE_COLUMNS},
    )
