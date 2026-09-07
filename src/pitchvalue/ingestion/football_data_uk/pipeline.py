"""End-to-end raw, staging, and canonical source import orchestration."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from pitchvalue.ingestion.football_data_uk.batch import (
    BatchCounters,
    ensure_provider,
    finish_batch,
    start_batch,
)
from pitchvalue.ingestion.football_data_uk.canonical import (
    CanonicalImportMetrics,
    import_staged_dataset,
)
from pitchvalue.ingestion.football_data_uk.downloader import FootballDataDownloader
from pitchvalue.ingestion.football_data_uk.parser import (
    CORE_COLUMNS,
    ParsedDataset,
    ParseError,
    parse_csv,
)
from pitchvalue.ingestion.football_data_uk.raw import RawArtifact, RawArtifactStore
from pitchvalue.ingestion.football_data_uk.registry import SourceDefinition
from pitchvalue.ingestion.football_data_uk.staging import stage_dataset

logger = logging.getLogger(__name__)


class LocalSourceError(ValueError):
    """Raised when a manual source file is not safe to import."""


@dataclass(frozen=True)
class SourceImportReport:
    """Auditable outcome for one source-file attempt."""

    source: str
    url: str
    fetch_status: str
    content_hash: str | None
    raw_path: str | None
    raw_rows: int
    parsed_rows: int
    staging_rejected: int
    staged: int
    batch_id: int
    batch_status: str
    canonical: CanonicalImportMetrics
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["canonical"] = asdict(self.canonical)
        return result


def _start(engine: Engine, source: SourceDefinition) -> tuple[int, int]:
    with engine.begin() as connection:
        provider_id = ensure_provider(connection)
        batch_id = start_batch(connection, provider_id, source.url)
    return provider_id, batch_id


def _failed_report(
    engine: Engine,
    source: SourceDefinition,
    batch_id: int,
    error: Exception,
    artifact: RawArtifact | None,
    dataset: ParsedDataset | None,
) -> SourceImportReport:
    with engine.begin() as connection:
        finish_batch(
            connection,
            batch_id,
            "failed",
            BatchCounters(rows_read=len(dataset.rows) if dataset else 0),
            source_hash=artifact.content_hash if artifact else None,
            error_summary=str(error),
        )
    return SourceImportReport(
        source=source.key,
        url=source.url,
        fetch_status="failed",
        content_hash=artifact.content_hash if artifact else None,
        raw_path=str(artifact.path.resolve()) if artifact else None,
        raw_rows=len(dataset.rows) if dataset else 0,
        parsed_rows=sum(not row.errors for row in dataset.rows) if dataset else 0,
        staging_rejected=0,
        staged=0,
        batch_id=batch_id,
        batch_status="failed",
        canonical=CanonicalImportMetrics(),
        error=str(error),
    )


def _canonicalize(
    engine: Engine,
    source: SourceDefinition,
    provider_id: int,
    batch_id: int,
    artifact: RawArtifact,
    dataset: ParsedDataset,
    acquisition_status: str,
) -> SourceImportReport:
    """Run the shared staging and canonical transaction for preserved bytes."""
    with engine.begin() as connection:
        staging = stage_dataset(connection, batch_id, source, dataset)
        canonical = import_staged_dataset(connection, batch_id, provider_id, source, dataset)
        rejected = staging.rows_rejected + canonical.rejected_canonical_rows
        status = "completed_with_errors" if rejected or canonical.ambiguous_matches else "completed"
        summaries: list[str] = []
        if staging.rows_rejected:
            summaries.append(f"{staging.rows_rejected} staging row(s) rejected")
        if canonical.rejected_canonical_rows:
            summaries.append(f"{canonical.rejected_canonical_rows} canonical row(s) rejected")
        if canonical.ambiguous_matches:
            summaries.append(f"{canonical.ambiguous_matches} ambiguous row(s)")
        finish_batch(
            connection,
            batch_id,
            status,
            BatchCounters(
                rows_read=staging.rows_read,
                rows_inserted=staging.rows_staged,
                rows_updated=canonical.statistics_updated,
                rows_rejected=rejected + canonical.ambiguous_matches,
            ),
            source_hash=artifact.content_hash,
            error_summary="; ".join(summaries) or None,
        )
    return SourceImportReport(
        source=source.key,
        url=source.url,
        fetch_status=acquisition_status,
        content_hash=artifact.content_hash,
        raw_path=str(artifact.path.resolve()),
        raw_rows=len(dataset.rows),
        parsed_rows=sum(not row.errors for row in dataset.rows),
        staging_rejected=staging.rows_rejected,
        staged=staging.rows_staged,
        batch_id=batch_id,
        batch_status=status,
        canonical=canonical,
    )


def import_source(
    engine: Engine,
    source: SourceDefinition,
    raw_root: Path,
    downloader: FootballDataDownloader,
) -> SourceImportReport:
    """Fetch and import one source with one atomic staging/canonical transaction."""
    provider_id, batch_id = _start(engine, source)
    artifact = None
    dataset = None
    try:
        artifact = downloader.fetch(source, RawArtifactStore(raw_root))
        dataset = parse_csv(artifact.path.read_bytes())
        return _canonicalize(
            engine,
            source,
            provider_id,
            batch_id,
            artifact,
            dataset,
            "already_preserved" if artifact.already_known else "downloaded",
        )
    except Exception as error:
        logger.exception("source import failed: %s", source.key)
        return _failed_report(engine, source, batch_id, error, artifact, dataset)


def validate_source_bytes(content: bytes, source: SourceDefinition) -> ParsedDataset:
    """Validate candidate bytes against one approved registry definition."""
    if not content:
        raise LocalSourceError("source file is empty")
    prefix = content[:4096].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<?xml")) or b"<html" in prefix:
        raise LocalSourceError("source appears to be HTML or an error page")
    try:
        dataset = parse_csv(content)
    except ParseError as error:
        raise LocalSourceError(str(error)) from error
    missing = sorted(set(CORE_COLUMNS).difference(dataset.columns))
    if missing:
        raise LocalSourceError(f"required CSV columns are missing: {', '.join(missing)}")
    if not dataset.rows:
        raise LocalSourceError("source CSV contains no data rows")
    divisions: set[str] = set()
    for row in dataset.rows:
        division = row.normalized_values.get("Div")
        if division is not None:
            divisions.add(division)
    if divisions != {source.source_code}:
        raise LocalSourceError(
            f"CSV division values {sorted(divisions)} do not match {source.source_code}"
        )
    return dataset


def validate_local_source(path: Path, source: SourceDefinition) -> tuple[bytes, ParsedDataset]:
    """Validate original manual bytes against one approved registry definition."""
    if not path.exists() or not path.is_file():
        raise LocalSourceError(f"local source file does not exist: {path}")
    content = path.read_bytes()
    return content, validate_source_bytes(content, source)


def import_local_source(
    engine: Engine,
    source: SourceDefinition,
    local_path: Path,
    raw_root: Path,
) -> SourceImportReport:
    """Import manual bytes through the same immutable raw, staging, and canonical layers."""
    provider_id, batch_id = _start(engine, source)
    artifact = None
    dataset = None
    try:
        content, dataset = validate_local_source(local_path, source)
        artifact = RawArtifactStore(raw_root).preserve(
            content,
            source,
            datetime.now(UTC),
            local_path.name,
            acquisition_mode="local_manual",
        )
        return _canonicalize(
            engine,
            source,
            provider_id,
            batch_id,
            artifact,
            dataset,
            "already_preserved" if artifact.already_known else "local_preserved",
        )
    except Exception as error:
        logger.exception("local source import failed: %s", source.key)
        return _failed_report(engine, source, batch_id, error, artifact, dataset)
