from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.config import load_settings
from pitchvalue.ingestion.football_data_uk.batch import (
    BatchCounters,
    BatchStateError,
    ensure_provider,
    finish_batch,
    start_batch,
)
from pitchvalue.ingestion.football_data_uk.downloader import FootballDataDownloader
from pitchvalue.ingestion.football_data_uk.parser import (
    ParseError,
    parse_csv,
    parse_nullable_decimal,
    parse_nullable_int,
    parse_source_date,
    parse_source_time,
)
from pitchvalue.ingestion.football_data_uk.profile import profile_dataset
from pitchvalue.ingestion.football_data_uk.raw import RawArtifactStore, sha256_bytes
from pitchvalue.ingestion.football_data_uk.registry import SOURCES, get_source
from pitchvalue.ingestion.football_data_uk.staging import stage_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "football_data_uk"


@pytest.fixture(scope="session")
def ingestion_engine() -> Iterator[Engine]:
    settings = load_settings(os.environ)
    engine = create_engine(settings.database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(ingestion_engine: Engine) -> Iterator[Connection]:
    with ingestion_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def test_parser_reads_valid_csv_and_preserves_raw_values() -> None:
    dataset = parse_csv((FIXTURES / "sample.csv").read_bytes())
    assert len(dataset.rows) == 6
    assert dataset.rows[0].raw_values["HomeTeam"] == "Alpha FC"
    assert dataset.rows[0].raw_values["B365H"] == "1.50"


def test_source_byte_sha256_is_stable() -> None:
    content = b"original,source,bytes\n"
    assert sha256_bytes(content) == sha256_bytes(content)
    assert len(sha256_bytes(content)) == 64


def test_changed_source_bytes_change_sha256() -> None:
    assert sha256_bytes(b"first") != sha256_bytes(b"second")


def test_blank_and_whitespace_cells_normalize_to_none() -> None:
    dataset = parse_csv((FIXTURES / "sample.csv").read_bytes())
    assert dataset.rows[2].normalized_values["HS"] is None
    assert dataset.rows[3].normalized_values["HS"] is None
    assert dataset.rows[3].raw_values["HS"] == "   "


def test_literal_zero_remains_numeric_zero() -> None:
    dataset = parse_csv((FIXTURES / "sample.csv").read_bytes())
    assert parse_nullable_int(dataset.rows[1].normalized_values["HS"]) == 0
    assert parse_nullable_decimal("0") == Decimal("0")


def test_malformed_integer_is_rejected() -> None:
    with pytest.raises(ParseError, match="invalid integer"):
        parse_nullable_int("not-an-int")


def test_malformed_decimal_is_rejected() -> None:
    with pytest.raises(ParseError, match="invalid decimal"):
        parse_nullable_decimal("not-a-decimal")


def test_malformed_numeric_row_is_reported() -> None:
    dataset = parse_csv((FIXTURES / "malformed.csv").read_bytes())
    assert dataset.rows[0].parsing_status == "rejected"
    assert len(dataset.rows[0].errors) == 2
    assert profile_dataset(dataset).numeric_parse_failures == 2


def test_missing_optional_columns_are_tolerated() -> None:
    dataset = parse_csv((FIXTURES / "minimal.csv").read_bytes())
    assert dataset.rows[0].parsing_status == "parsed"
    assert "HS" not in dataset.columns


def test_unknown_extra_column_is_preserved() -> None:
    dataset = parse_csv((FIXTURES / "sample.csv").read_bytes())
    assert dataset.rows[0].raw_values["UnknownColumn"] == "kept"


def test_row_hash_is_deterministic_and_profiles_duplicates() -> None:
    content = (FIXTURES / "sample.csv").read_bytes()
    first = parse_csv(content)
    second = parse_csv(content)
    assert first.rows[0].row_hash == second.rows[0].row_hash
    assert first.rows[4].row_hash == first.rows[5].row_hash
    assert profile_dataset(first).duplicate_raw_row_hashes == 1


def test_date_and_time_parsing_are_explicit_and_nullable() -> None:
    assert parse_source_date("16/08/2024") is not None
    assert parse_source_date("16/08/24") is not None
    assert parse_source_time("20:00") is not None
    assert parse_source_time("") is None
    with pytest.raises(ParseError, match="invalid date"):
        parse_source_date("08/16/2024")


def test_profile_reports_columns_missingness_and_core_availability() -> None:
    profile = profile_dataset(parse_csv((FIXTURES / "sample.csv").read_bytes()))
    assert profile.row_count == 6
    assert profile.missingness["HS"] == 2
    assert profile.core_column_availability["HomeTeam"] is True
    assert profile.date_parse_failures == 0


def test_raw_artifact_storage_is_immutable_and_content_addressed(tmp_path: Path) -> None:
    source = get_source("E0:2024/25")
    store = RawArtifactStore(tmp_path)
    fetched_at = datetime(2026, 9, 8, tzinfo=UTC)
    first = store.preserve(b"same bytes", source, fetched_at, "E0.csv")
    repeated = store.preserve(b"same bytes", source, fetched_at, "E0.csv")
    changed = store.preserve(b"changed bytes", source, fetched_at, "E0.csv")
    assert first.already_known is False
    assert repeated.already_known is True
    assert repeated.path == first.path
    assert changed.path != first.path
    assert first.path.read_bytes() == b"same bytes"
    assert first.metadata_path.exists()


def test_downloader_uses_http_boundary_and_preserves_response(tmp_path: Path) -> None:
    source = get_source("E0:2024/25")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"Div,Date\nE0,16/08/2024\n", request=request)
    )
    with httpx.Client(transport=transport) as client:
        downloader = FootballDataDownloader(client)
        artifact = downloader.fetch(source, RawArtifactStore(tmp_path))
    assert artifact.path.read_bytes() == b"Div,Date\nE0,16/08/2024\n"


def test_registry_has_only_approved_domestic_scope() -> None:
    assert len(SOURCES) == 14
    assert {source.canonical_competition for source in SOURCES} == {
        "Premier League",
        "Ligue 1",
        "Bundesliga",
        "Süper Lig",
        "Primeira Liga",
        "La Liga",
        "Scottish Premiership",
    }
    assert {source.season_name for source in SOURCES} == {"2024/25", "2025/26"}
    assert all("UEFA" not in source.canonical_competition for source in SOURCES)
    assert all(source.enabled for source in SOURCES)


def test_registry_codes_and_urls_are_explicit() -> None:
    assert {source.source_code for source in SOURCES} == {
        "E0",
        "F1",
        "D1",
        "T1",
        "P1",
        "SP1",
        "SC0",
    }
    assert get_source("SC0:2025/26").url.endswith("/mmz4281/2526/SC0.csv")


def test_raw_directory_is_ignored_but_synthetic_fixtures_are_not() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "data/raw/football_data_uk/E0.csv"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    fixture = subprocess.run(
        ["git", "check-ignore", "tests/fixtures/football_data_uk/sample.csv"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0
    assert fixture.returncode == 1
    assert (FIXTURES / "sample.csv").exists()


@pytest.mark.integration
def test_provider_and_batch_start_are_idempotent_and_auditable(db: Connection) -> None:
    first_provider_id = ensure_provider(db)
    second_provider_id = ensure_provider(db)
    batch_id = start_batch(db, first_provider_id, "synthetic:test")
    row = db.execute(
        text(
            """
            SELECT provider_id, source_identifier, status
            FROM import_batches WHERE import_batch_id = :batch_id
            """
        ),
        {"batch_id": batch_id},
    ).one()
    assert first_provider_id == second_provider_id
    assert tuple(row) == (first_provider_id, "synthetic:test", "running")


@pytest.mark.integration
@pytest.mark.parametrize("status", ["completed", "completed_with_errors", "failed"])
def test_batch_terminal_transitions(db: Connection, status: str) -> None:
    batch_id = start_batch(db, ensure_provider(db), "synthetic:test")
    finish_batch(
        db,
        batch_id,
        status,
        BatchCounters(rows_read=2, rows_inserted=1, rows_rejected=1),
        source_hash="a" * 64,
        error_summary="synthetic error" if status != "completed" else None,
    )
    row = db.execute(
        text(
            """
            SELECT status, rows_read, rows_inserted, rows_rejected,
                   completed_at IS NOT NULL
            FROM import_batches WHERE import_batch_id = :batch_id
            """
        ),
        {"batch_id": batch_id},
    ).one()
    assert tuple(row) == (status, 2, 1, 1, True)
    with pytest.raises(BatchStateError):
        finish_batch(db, batch_id, "failed", BatchCounters())


@pytest.mark.integration
def test_batch_counters_cannot_be_negative(db: Connection) -> None:
    batch_id = start_batch(db, ensure_provider(db), "synthetic:test")
    with pytest.raises(IntegrityError), db.begin_nested():
        finish_batch(db, batch_id, "failed", BatchCounters(rows_read=-1))


@pytest.mark.integration
def test_orphan_staging_batch_is_rejected(db: Connection) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                """
                INSERT INTO football_data_staging_rows (
                    import_batch_id, source_row_number, competition_source_code,
                    season_name, raw_row, row_hash, parsing_status
                ) VALUES (
                    9223372036854770000, 2, 'E0', '2024/25', '{}'::jsonb,
                    :row_hash, 'parsed'
                )
                """
            ),
            {"row_hash": "a" * 64},
        )


@pytest.mark.integration
def test_staging_is_idempotent_within_batch_source_row(db: Connection) -> None:
    batch_id = start_batch(db, ensure_provider(db), "synthetic:test")
    source = get_source("E0:2024/25")
    dataset = parse_csv((FIXTURES / "minimal.csv").read_bytes())
    first = stage_dataset(db, batch_id, source, dataset)
    repeated = stage_dataset(db, batch_id, source, dataset)
    assert first.rows_staged == 1
    assert repeated.rows_staged == 0
    assert repeated.rows_already_known == 1


@pytest.mark.integration
def test_staging_preserves_odds_and_unknown_source_columns(db: Connection) -> None:
    batch_id = start_batch(db, ensure_provider(db), "synthetic:test")
    source = get_source("E0:2024/25")
    dataset = parse_csv((FIXTURES / "sample.csv").read_bytes())
    result = stage_dataset(db, batch_id, source, dataset)
    row = db.execute(
        text(
            """
            SELECT raw_row ->> 'B365H', raw_row ->> 'UnknownColumn'
            FROM football_data_staging_rows
            WHERE import_batch_id = :batch_id AND source_row_number = 2
            """
        ),
        {"batch_id": batch_id},
    ).one()
    assert result.rows_staged == 6
    assert tuple(row) == ("1.50", "kept")
