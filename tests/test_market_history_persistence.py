from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.markets.history.config import FOOTBALL_DATA_MAPPINGS
from pitchvalue.markets.history.contracts import (
    HistoricalOddsError,
    HistoricalPriceObservation,
    HistoricalSourceRow,
)
from pitchvalue.markets.history.football_data import normalize_source_value
from pitchvalue.markets.history.repository import persist_historical_observation
from pitchvalue.markets.history.source import (
    inventory_supported_fields,
    iter_canonical_source_rows,
    replayed_source_row_count,
    validate_replay_consistency,
)


@pytest.fixture(scope="session")
def history_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(history_engine: Engine) -> Iterator[Connection]:
    with history_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _id(db: Connection, statement: str, values: Mapping[str, object] | None = None) -> int:
    value = db.execute(text(statement), values or {}).scalar_one()
    assert isinstance(value, int)
    return value


def _source_context(db: Connection) -> int:
    provider_id = _id(
        db,
        """
        INSERT INTO providers(name,provider_type,priority)
        VALUES ('History Odds Provider','historical_csv',1) RETURNING provider_id
        """,
    )
    competition_id = _id(
        db,
        """
        INSERT INTO competitions(canonical_name,country_code,competition_type)
        VALUES ('History Test League','TST','domestic_league') RETURNING competition_id
        """,
    )
    season_id = _id(
        db,
        """
        INSERT INTO seasons(competition_id,season_name,start_year,end_year,status)
        VALUES (:competition_id,'2098/99',2098,2099,'completed') RETURNING season_id
        """,
        {"competition_id": competition_id},
    )
    home_id = _id(
        db,
        """
        INSERT INTO teams(canonical_name,normalized_name)
        VALUES ('History Home','history home') RETURNING team_id
        """,
    )
    away_id = _id(
        db,
        """
        INSERT INTO teams(canonical_name,normalized_name)
        VALUES ('History Away','history away') RETURNING team_id
        """,
    )
    match_id = _id(
        db,
        """
        INSERT INTO matches(
            competition_id,season_id,kickoff_at_utc,home_team_id,away_team_id,status
        ) VALUES (
            :competition_id,:season_id,:kickoff,:home,:away,'SCHEDULED'
        ) RETURNING match_id
        """,
        {
            "competition_id": competition_id,
            "season_id": season_id,
            "kickoff": datetime(2099, 1, 2, tzinfo=UTC),
            "home": home_id,
            "away": away_id,
        },
    )
    raw = (
        '{"B365H":"2.10","B365D":"3.20","B365A":"3.40",'
        '"B365CH":"2.00","B365CD":"3.30","B365CA":"3.60"}'
    )
    for _ in ("first", "replay"):
        batch_id = _id(
            db,
            """
            INSERT INTO import_batches(
                provider_id,started_at,source_identifier,rows_read,status
            ) VALUES (:provider,:started,:source,1,'completed') RETURNING import_batch_id
            """,
            {
                "provider": provider_id,
                "started": datetime(2099, 1, 3, tzinfo=UTC),
                "source": "history.csv",
            },
        )
        staging_id = _id(
            db,
            """
            INSERT INTO football_data_staging_rows(
                import_batch_id,source_row_number,competition_source_code,
                season_name,raw_row,row_hash,parsing_status
            ) VALUES (
                :batch,2,'E0','2025/26',CAST(:raw AS jsonb),repeat('b',64),'parsed'
            ) RETURNING staging_row_id
            """,
            {"batch": batch_id, "raw": raw},
        )
        db.execute(
            text(
                """
                INSERT INTO football_data_canonical_lineage(staging_row_id,match_id)
                VALUES (:staging,:match)
                """
            ),
            {"staging": staging_id, "match": match_id},
        )
    db.execute(
        text(
            """
            INSERT INTO match_provider_refs (
                match_id,provider_id,source_url,source_record_hash
            ) VALUES (:match,:provider,'history.csv',repeat('b',64))
            """
        ),
        {"match": match_id, "provider": provider_id},
    )
    return match_id


def _row(db: Connection, match_id: int) -> HistoricalSourceRow:
    return next(row for row in iter_canonical_source_rows(db) if row.match_id == match_id)


def test_source_reader_chooses_stable_representative(db: Connection) -> None:
    match_id = _source_context(db)
    rows = tuple(row for row in iter_canonical_source_rows(db) if row.match_id == match_id)
    assert len(rows) == 1
    assert rows[0].value("B365H") == "2.10"
    assert replayed_source_row_count(db) >= 1


def test_inventory_reports_supported_fields(db: Connection) -> None:
    _source_context(db)
    items = tuple(item for item in inventory_supported_fields(db) if item.source_code == "E0")
    assert len(items) == 6
    assert all(item.present_count == 1 and item.missing_count == 0 for item in items)


def test_persistence_is_atomic_and_idempotent(db: Connection) -> None:
    match_id = _source_context(db)
    observation = normalize_source_value(_row(db, match_id), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(observation, HistoricalPriceObservation)
    assert persist_historical_observation(db, observation) is True
    assert persist_historical_observation(db, observation) is False
    stored = db.execute(
        text(
            """
            SELECT decimal_odds,source_staging_row_id,source_field,quality_reasons
            FROM odds_snapshots WHERE match_id=:match
            """
        ),
        {"match": match_id},
    ).one()
    assert stored.decimal_odds == Decimal("2.1000")
    assert stored.source_staging_row_id == observation.source_staging_row_id
    assert stored.source_field == "B365H"
    assert stored.quality_reasons == ["timestamp_uncertain"]


def test_different_source_fields_are_distinct(db: Connection) -> None:
    match_id = _source_context(db)
    row = _row(db, match_id)
    first = normalize_source_value(row, FOOTBALL_DATA_MAPPINGS[0])
    second = normalize_source_value(row, FOOTBALL_DATA_MAPPINGS[1])
    assert isinstance(first, HistoricalPriceObservation)
    assert isinstance(second, HistoricalPriceObservation)
    assert persist_historical_observation(db, first) is True
    assert persist_historical_observation(db, second) is True


def test_different_versions_are_distinct(db: Connection) -> None:
    match_id = _source_context(db)
    first = normalize_source_value(_row(db, match_id), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(first, HistoricalPriceObservation)
    second = replace(first, normalization_version="historical_odds_normalization_v2")
    assert persist_historical_observation(db, first) is True
    assert persist_historical_observation(db, second) is True


def test_persisted_rows_have_complete_lineage(db: Connection) -> None:
    match_id = _source_context(db)
    row = _row(db, match_id)
    for mapping in FOOTBALL_DATA_MAPPINGS:
        observation = normalize_source_value(row, mapping)
        assert isinstance(observation, HistoricalPriceObservation)
        assert persist_historical_observation(db, observation)
    lineage = db.execute(
        text(
            """
            SELECT count(*) FROM odds_snapshots
            WHERE match_id=:match AND source_staging_row_id IS NOT NULL
              AND source_field IS NOT NULL
            """
        ),
        {"match": match_id},
    ).scalar_one()
    assert lineage == 6


def test_divergent_replay_is_rejected(db: Connection) -> None:
    match_id = _source_context(db)
    staging_id = db.execute(
        text(
            """
            SELECT max(staging_row_id) FROM football_data_canonical_lineage
            WHERE match_id=:match
            """
        ),
        {"match": match_id},
    ).scalar_one()
    db.execute(
        text(
            """
            UPDATE football_data_staging_rows SET row_hash=repeat('c',64)
            WHERE staging_row_id=:staging
            """
        ),
        {"staging": staging_id},
    )
    with pytest.raises(HistoricalOddsError, match="divergent staging replays"):
        validate_replay_consistency(db)
