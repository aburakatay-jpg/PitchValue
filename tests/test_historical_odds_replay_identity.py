from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.config import load_settings
from pitchvalue.markets.history.config import FOOTBALL_DATA_MAPPINGS
from pitchvalue.markets.history.contracts import HistoricalPriceObservation, HistoricalSourceRow
from pitchvalue.markets.history.football_data import normalize_source_value
from pitchvalue.markets.history.repository import persist_historical_observation


@pytest.fixture(scope="session")
def replay_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(replay_engine: Engine) -> Iterator[Connection]:
    with replay_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _id(db: Connection, statement: str, values: Mapping[str, object] | None = None) -> int:
    value = db.execute(text(statement), values or {}).scalar_one()
    assert isinstance(value, int)
    return value


def _context(
    db: Connection, label: str = "Primary"
) -> tuple[HistoricalSourceRow, HistoricalSourceRow, int]:
    provider_id = _id(
        db,
        """INSERT INTO providers(name,provider_type,priority)
        VALUES (:name,'historical_csv',1) RETURNING provider_id""",
        {"name": f"Replay Identity Provider {label}"},
    )
    competition_id = _id(
        db,
        """INSERT INTO competitions(canonical_name,country_code,competition_type)
        VALUES (:name,'TST','domestic_league') RETURNING competition_id""",
        {"name": f"Replay Identity League {label}"},
    )
    season_id = _id(
        db,
        """INSERT INTO seasons(competition_id,season_name,start_year,end_year,status)
        VALUES (:competition,'2098/99',2098,2099,'completed') RETURNING season_id""",
        {"competition": competition_id},
    )
    home_id = _id(
        db,
        """INSERT INTO teams(canonical_name,normalized_name)
        VALUES (:name,:normalized) RETURNING team_id""",
        {"name": f"Replay Home {label}", "normalized": f"replay home {label.lower()}"},
    )
    away_id = _id(
        db,
        """INSERT INTO teams(canonical_name,normalized_name)
        VALUES (:name,:normalized) RETURNING team_id""",
        {"name": f"Replay Away {label}", "normalized": f"replay away {label.lower()}"},
    )
    match_id = _id(
        db,
        """INSERT INTO matches(competition_id,season_id,home_team_id,away_team_id,status)
        VALUES (:competition,:season,:home,:away,'SCHEDULED') RETURNING match_id""",
        {
            "competition": competition_id,
            "season": season_id,
            "home": home_id,
            "away": away_id,
        },
    )
    source_url = f"https://example.invalid/replay-{label.lower()}.csv"
    row_hash = ("d" if label == "Primary" else "e") * 64
    staging_ids: list[int] = []
    for day in (1, 2):
        batch_id = _id(
            db,
            """INSERT INTO import_batches(
                provider_id,started_at,source_identifier,rows_read,status
            ) VALUES (:provider,:started,:source,1,'completed') RETURNING import_batch_id""",
            {
                "provider": provider_id,
                "started": datetime(2099, 1, day, tzinfo=UTC),
                "source": source_url,
            },
        )
        staging_ids.append(
            _id(
                db,
                """INSERT INTO football_data_staging_rows(
                    import_batch_id,source_row_number,competition_source_code,season_name,
                    raw_row,row_hash,parsing_status
                ) VALUES (
                    :batch,2,'E0','2098/99','{"B365H":"2.10"}'::jsonb,:hash,'parsed'
                ) RETURNING staging_row_id""",
                {"batch": batch_id, "hash": row_hash},
            )
        )
    source_ref = _id(
        db,
        """INSERT INTO match_provider_refs(
            match_id,provider_id,source_url,source_record_hash
        ) VALUES (:match,:provider,:source,:hash) RETURNING match_provider_ref_id""",
        {"match": match_id, "provider": provider_id, "source": source_url, "hash": row_hash},
    )
    raw_values = (("B365H", "2.10"),)
    rows = tuple(
        HistoricalSourceRow(
            match_id=match_id,
            competition_id=competition_id,
            competition_name=f"Replay Identity League {label}",
            season_id=season_id,
            provider_id=provider_id,
            staging_row_id=staging_id,
            source_row_number=2,
            source_code="E0",
            season_name="2098/99",
            event_at=datetime(2099, 1, 3, tzinfo=UTC),
            source_record_hash=row_hash,
            raw_values=raw_values,
        )
        for staging_id in staging_ids
    )
    return rows[0], rows[1], source_ref


def _observation(row: HistoricalSourceRow) -> HistoricalPriceObservation:
    value = normalize_source_value(row, FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(value, HistoricalPriceObservation)
    return value


def test_different_replay_staging_rows_reuse_one_canonical_observation(db: Connection) -> None:
    first_row, replay_row, source_ref = _context(db)
    assert first_row.staging_row_id != replay_row.staging_row_id
    assert first_row.source_record_hash == replay_row.source_record_hash
    assert persist_historical_observation(db, _observation(first_row)) is True
    assert persist_historical_observation(db, _observation(replay_row)) is False
    stored = db.execute(
        text(
            """SELECT count(*),min(source_match_provider_ref_id)
            FROM odds_snapshots WHERE match_id=:match"""
        ),
        {"match": first_row.match_id},
    ).one()
    assert stored == (1, source_ref)


def test_same_staging_semantic_observation_cannot_duplicate(db: Connection) -> None:
    first_row, _, _ = _context(db)
    observation = _observation(first_row)
    assert persist_historical_observation(db, observation) is True
    assert persist_historical_observation(db, observation) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_field", "B365D"),
        ("mapping_version", "football_data_mapping_v2"),
        ("normalization_version", "historical_odds_normalization_v2"),
        ("quality_policy_version", "football_data_quality_v2"),
    ],
)
def test_versioned_identity_dimensions_remain_distinct(
    db: Connection, field: str, value: str
) -> None:
    first_row, _, _ = _context(db)
    observation = _observation(first_row)
    assert persist_historical_observation(db, observation) is True
    if field == "source_field":
        changed = replace(observation, source_field=value)
    elif field == "mapping_version":
        changed = replace(observation, mapping_version=value)
    elif field == "normalization_version":
        changed = replace(observation, normalization_version=value)
    else:
        changed = replace(observation, quality_policy_version=value)
    assert persist_historical_observation(db, changed) is True


def test_different_stable_source_record_with_same_price_is_distinct(db: Connection) -> None:
    first_row, _, _ = _context(db)
    first = _observation(first_row)
    assert persist_historical_observation(db, first) is True
    second_row, _, _ = _context(db, "Secondary")
    second = _observation(second_row)
    assert second.decimal_odds == first.decimal_odds == Decimal("2.10")
    assert persist_historical_observation(db, second) is True


def test_provider_source_record_identity_is_database_enforced(db: Connection) -> None:
    first_row, _, _ = _context(db)
    row = (
        db.execute(
            text(
                """SELECT r.match_id,r.provider_id,r.source_url,r.source_record_hash
            FROM match_provider_refs r WHERE r.match_id=:match"""
            ),
            {"match": first_row.match_id},
        )
        .mappings()
        .one()
    )
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                """INSERT INTO match_provider_refs(
                    match_id,provider_id,source_url,source_record_hash
                ) VALUES (:match_id,:provider_id,:source_url,:source_record_hash)"""
            ),
            dict(row),
        )


def test_historical_stable_identity_is_required(db: Connection) -> None:
    first_row, _, _ = _context(db)
    observation = _observation(first_row)
    assert persist_historical_observation(db, observation)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                """UPDATE odds_snapshots SET source_match_provider_ref_id=NULL
                WHERE match_id=:match"""
            ),
            {"match": first_row.match_id},
        )


def test_staging_and_provider_record_delete_are_restricted(db: Connection) -> None:
    first_row, _, source_ref = _context(db)
    assert persist_historical_observation(db, _observation(first_row))
    for statement, value in (
        (
            "DELETE FROM football_data_staging_rows WHERE staging_row_id=:value",
            first_row.staging_row_id,
        ),
        ("DELETE FROM match_provider_refs WHERE match_provider_ref_id=:value", source_ref),
    ):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text(statement), {"value": value})


def test_historical_unique_index_uses_replay_stable_reference(db: Connection) -> None:
    definition = db.execute(
        text(
            """SELECT indexdef FROM pg_indexes
            WHERE tablename='odds_snapshots'
              AND indexname='uq_odds_historical_source_identity'"""
        )
    ).scalar_one()
    assert "source_match_provider_ref_id" in definition
    assert "source_staging_row_id" not in definition


def test_existing_historical_rows_have_replay_stable_identity(db: Connection) -> None:
    first_row, _, _ = _context(db)
    assert persist_historical_observation(db, _observation(first_row))
    total, missing = db.execute(
        text(
            """SELECT count(*),count(*) FILTER(WHERE source_match_provider_ref_id IS NULL)
            FROM odds_snapshots WHERE observation_origin='historical_source'"""
        )
    ).one()
    assert total >= 1
    assert missing == 0
