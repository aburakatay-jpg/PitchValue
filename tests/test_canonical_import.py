from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.ingestion.football_data_uk.batch import ensure_provider, start_batch
from pitchvalue.ingestion.football_data_uk.canonical import (
    CanonicalImportError,
    CanonicalImportMetrics,
    import_staged_dataset,
    local_kickoff_to_utc,
    normalize_team_name,
)
from pitchvalue.ingestion.football_data_uk.downloader import FootballDataDownloader
from pitchvalue.ingestion.football_data_uk.parser import parse_csv
from pitchvalue.ingestion.football_data_uk.pipeline import import_source
from pitchvalue.ingestion.football_data_uk.registry import SourceDefinition, get_source
from pitchvalue.ingestion.football_data_uk.staging import stage_dataset


@pytest.fixture(scope="session")
def canonical_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(canonical_engine: Engine) -> Iterator[Connection]:
    with canonical_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def csv_bytes(*rows: str, optional: bool = True) -> bytes:
    header = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,Referee"
    if optional:
        header += ",HS,AS,HST,AST,HC,AC,HF,AF,HY,AY,HR,AR,B365H"
    return (header + "\n" + "\n".join(rows) + "\n").encode()


def import_dataset(
    db: Connection, content: bytes, source_key: str = "E0:2024/25"
) -> tuple[CanonicalImportMetrics, int, int]:
    source = get_source(source_key)
    provider_id = ensure_provider(db)
    batch_id = start_batch(db, provider_id, source.url)
    dataset = parse_csv(content)
    stage_dataset(db, batch_id, source, dataset)
    metrics = import_staged_dataset(db, batch_id, provider_id, source, dataset)
    return metrics, batch_id, provider_id


def scalar(db: Connection, query: str) -> int:
    value = db.execute(text(query)).scalar_one()
    assert isinstance(value, int)
    return value


def test_normalization_is_conservative_and_not_fuzzy() -> None:
    assert normalize_team_name("  Paris   Saint‑Germain  ") == "paris saint-germain"
    assert normalize_team_name("St. John’s FC") == "st. john's fc"
    assert normalize_team_name("Manchester United") != normalize_team_name("Manchester Utd")


def test_timezone_conversion_is_dst_safe() -> None:
    assert local_kickoff_to_utc("15/01/2025", "12:00", "ENG") == datetime(
        2025, 1, 15, 12, tzinfo=UTC
    )
    assert local_kickoff_to_utc("15/07/2025", "12:00", "ENG") == datetime(
        2025, 7, 15, 11, tzinfo=UTC
    )


@pytest.mark.integration
def test_full_replay_reuses_season_teams_aliases_matches_refs_and_stats(db: Connection) -> None:
    content = csv_bytes(
        "E0,16/08/2024,20:00,Alpha FC,Beta FC,2,1,H,1,0,Ref A,10,8,4,3,5,2,7,9,1,2,0,0,1.50",
        "E0,17/08/2024,15:00,Beta FC,Gamma FC,0,1,A,0,0,Ref B,0,9,0,2,0,4,8,6,0,1,0,0,2.00",
    )
    first, _, _ = import_dataset(db, content)
    counts_after_first = tuple(
        scalar(db, f"SELECT count(*) FROM {table}")
        for table in (
            "seasons",
            "teams",
            "team_aliases",
            "matches",
            "match_provider_refs",
            "match_statistics",
            "data_quality",
        )
    )
    second, _, _ = import_dataset(db, content)
    counts_after_second = tuple(
        scalar(db, f"SELECT count(*) FROM {table}")
        for table in (
            "seasons",
            "teams",
            "team_aliases",
            "matches",
            "match_provider_refs",
            "match_statistics",
            "data_quality",
        )
    )
    assert first.seasons_created == 1
    assert first.teams_created == 3
    assert first.aliases_created == 3
    assert first.matches_created == 2
    assert first.statistics_created == 2
    assert second.seasons_reused == 1
    assert second.matches_created == 0
    assert second.matches_reused == 2
    assert second.provider_refs_created == 0
    assert second.statistics_reused == 2
    assert counts_after_second == counts_after_first


@pytest.mark.integration
def test_valid_results_and_score_semantics(db: Connection) -> None:
    content = csv_bytes(
        "E0,16/08/2024,20:00,Home A,Away A,1,0,H,,,,,,,,,,,,,,,,",
        "E0,17/08/2024,20:00,Home B,Away B,1,1,D,,,,,,,,,,,,,,,,",
        "E0,18/08/2024,20:00,Home C,Away C,0,2,A,,,,,,,,,,,,,,,,",
    )
    metrics, _, _ = import_dataset(db, content)
    results = db.execute(text("SELECT result FROM matches ORDER BY result")).scalars().all()
    assert metrics.matches_created == 3
    assert results == ["A", "D", "H"]


@pytest.mark.integration
def test_contradictory_result_and_paired_halftime_are_rejected(db: Connection) -> None:
    content = csv_bytes(
        "E0,16/08/2024,20:00,Alpha,Beta,2,1,A,1,0,,,,,,,,,,,,,",
        "E0,17/08/2024,20:00,Gamma,Delta,1,0,H,1,,,,,,,,,,,,,,",
    )
    metrics, _, _ = import_dataset(db, content)
    assert metrics.rejected_canonical_rows == 2
    assert scalar(db, "SELECT count(*) FROM matches") == 0


@pytest.mark.integration
def test_blank_halftime_and_date_only_do_not_fabricate_values(db: Connection) -> None:
    content = csv_bytes("E0,16/08/2024,,Alpha,Beta,0,0,D,,,,,,,,,,,,,,,,")
    metrics, _, _ = import_dataset(db, content)
    row = db.execute(text("SELECT kickoff_at_utc, home_ht_score, away_ht_score FROM matches")).one()
    assert metrics.matches_created == 1
    assert tuple(row) == (None, None, None)


@pytest.mark.integration
def test_stats_missing_zero_creation_and_quality_flags(db: Connection) -> None:
    content = csv_bytes(
        "E0,16/08/2024,20:00,Alpha,Beta,0,0,D,,,,,,,,,,,,,,,,",
        "E0,17/08/2024,20:00,Gamma,Delta,1,0,H,,,,0,,,,,,,,,,,,",
    )
    metrics, _, _ = import_dataset(db, content)
    stats = db.execute(text("SELECT home_shots FROM match_statistics")).scalar_one()
    qualities = db.execute(
        text(
            "SELECT result_available, stats_available, odds_available, xg_available "
            "FROM data_quality ORDER BY stats_available"
        )
    ).all()
    assert metrics.statistics_created == 1
    assert stats == 0
    assert [tuple(row) for row in qualities] == [
        (True, False, False, False),
        (True, True, False, False),
    ]
    assert scalar(db, "SELECT count(*) FROM odds_snapshots") == 0


@pytest.mark.integration
def test_malformed_optional_stat_rejects_whole_row_in_staging(db: Connection) -> None:
    content = csv_bytes("E0,16/08/2024,20:00,Alpha,Beta,1,0,H,,,,bad,,,,,,,,,,,,")
    metrics, batch_id, _ = import_dataset(db, content)
    status = db.execute(
        text(
            "SELECT parsing_status FROM football_data_staging_rows WHERE import_batch_id=:batch_id"
        ),
        {"batch_id": batch_id},
    ).scalar_one()
    assert status == "rejected"
    assert metrics.matches_created == 0


@pytest.mark.integration
def test_no_fuzzy_merge_for_similar_names(db: Connection) -> None:
    import_dataset(
        db,
        csv_bytes("E0,16/08/2024,20:00,Manchester United,Beta,1,0,H,,,,,,,,,,,,,,,,"),
    )
    import_dataset(
        db,
        csv_bytes("E0,17/08/2024,20:00,Manchester Utd,Gamma,1,0,H,,,,,,,,,,,,,,,,"),
    )
    assert (
        scalar(
            db,
            "SELECT count(*) FROM teams WHERE normalized_name LIKE 'manchester u%';",
        )
        == 2
    )


@pytest.mark.integration
def test_invalid_division_and_negative_score_are_rejected(db: Connection) -> None:
    content = csv_bytes(
        "F1,16/08/2024,20:00,Alpha,Beta,1,0,H,,,,,,,,,,,,,,,,",
        "E0,17/08/2024,20:00,Gamma,Delta,-1,0,A,,,,,,,,,,,,,,,,",
    )
    metrics, _, _ = import_dataset(db, content)
    assert metrics.rejected_canonical_rows == 2
    assert scalar(db, "SELECT count(*) FROM matches") == 0


@pytest.mark.integration
def test_orphan_canonical_competition_rolls_back_source_transaction(db: Connection) -> None:
    source = SourceDefinition(
        "Missing Competition", "2024/25", "football-data.co.uk", "E0", "GBR", "ENG", "x"
    )
    provider_id = ensure_provider(db)
    batch_id = start_batch(db, provider_id, source.url)
    dataset = parse_csv(csv_bytes("E0,16/08/2024,20:00,Alpha,Beta,1,0,H,,,,,,,,,,,,,,,,"))
    before = scalar(db, "SELECT count(*) FROM teams")
    with pytest.raises(CanonicalImportError), db.begin_nested():
        stage_dataset(db, batch_id, source, dataset)
        import_staged_dataset(db, batch_id, provider_id, source, dataset)
    assert scalar(db, "SELECT count(*) FROM teams") == before


@pytest.mark.integration
def test_pipeline_failure_marks_batch_and_rolls_back_staging(
    canonical_engine: Engine, tmp_path: Path
) -> None:
    source = SourceDefinition(
        "Missing Competition",
        "2024/25",
        "football-data.co.uk",
        "E0",
        "GBR",
        "ENG",
        "https://synthetic.invalid/E0.csv",
    )
    content = csv_bytes("E0,16/08/2024,20:00,Alpha,Beta,1,0,H,,,,,,,,,,,,,,,,")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=content, request=request)
    )
    with httpx.Client(transport=transport) as client:
        report = import_source(canonical_engine, source, tmp_path, FootballDataDownloader(client))
    with canonical_engine.begin() as connection:
        assert report.batch_status == "failed"
        assert (
            connection.execute(
                text("SELECT status FROM import_batches WHERE import_batch_id=:id"),
                {"id": report.batch_id},
            ).scalar_one()
            == "failed"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM football_data_staging_rows WHERE import_batch_id=:id"),
                {"id": report.batch_id},
            ).scalar_one()
            == 0
        )
        connection.execute(
            text("DELETE FROM import_batches WHERE import_batch_id=:id"),
            {"id": report.batch_id},
        )
