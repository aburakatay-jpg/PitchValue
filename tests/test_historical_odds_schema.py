from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.config import load_settings
from pitchvalue.markets.history import (
    ObservationOrigin,
    ObservationRole,
    ObservationSourceKind,
    OddsQualityStatus,
    TimingSemantics,
)


@pytest.fixture(scope="session")
def odds_schema_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(odds_schema_engine: Engine) -> Iterator[Connection]:
    with odds_schema_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _id(db: Connection, statement: str, parameters: Mapping[str, object] | None = None) -> int:
    value = db.execute(text(statement), parameters or {}).scalar_one()
    assert isinstance(value, int)
    return value


def _reject(db: Connection, statement: str, parameters: Mapping[str, object]) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text(statement), parameters)


def _context(db: Connection) -> dict[str, int]:
    provider_id = _id(
        db,
        """
        INSERT INTO providers (name, provider_type, priority)
        VALUES ('Historical Odds Schema Provider', 'football_data', 1)
        RETURNING provider_id
        """,
    )
    competition_id = _id(
        db,
        """
        INSERT INTO competitions (canonical_name, country_code, competition_type)
        VALUES ('Historical Odds Schema Competition', 'TST', 'domestic_league')
        RETURNING competition_id
        """,
    )
    season_id = _id(
        db,
        """
        INSERT INTO seasons (competition_id, season_name, start_year, end_year, status)
        VALUES (:competition_id, '2098/99', 2098, 2099, 'completed')
        RETURNING season_id
        """,
        {"competition_id": competition_id},
    )
    home_team_id = _id(
        db,
        """
        INSERT INTO teams (canonical_name, normalized_name)
        VALUES ('Historical Odds Home', 'historical odds home') RETURNING team_id
        """,
    )
    away_team_id = _id(
        db,
        """
        INSERT INTO teams (canonical_name, normalized_name)
        VALUES ('Historical Odds Away', 'historical odds away') RETURNING team_id
        """,
    )
    match_id = _id(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (
            :competition_id, :season_id, :home_team_id, :away_team_id, 'SCHEDULED'
        ) RETURNING match_id
        """,
        {
            "competition_id": competition_id,
            "season_id": season_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        },
    )
    batch_id = _id(
        db,
        """
        INSERT INTO import_batches (
            provider_id, started_at, source_identifier, rows_read, status
        ) VALUES (
            :provider_id, :started_at, 'historical-odds-schema.csv', 1, 'completed'
        ) RETURNING import_batch_id
        """,
        {"provider_id": provider_id, "started_at": datetime(2099, 1, 1, tzinfo=UTC)},
    )
    staging_row_id = _id(
        db,
        """
        INSERT INTO football_data_staging_rows (
            import_batch_id, source_row_number, competition_source_code,
            season_name, raw_row, row_hash, parsing_status
        ) VALUES (
            :batch_id, 2, 'TST', '2098/99', '{}'::jsonb,
            repeat('a', 64), 'parsed'
        ) RETURNING staging_row_id
        """,
        {"batch_id": batch_id},
    )
    return {
        "provider_id": provider_id,
        "match_id": match_id,
        "source_staging_row_id": staging_row_id,
    }


HISTORICAL_INSERT = """
    INSERT INTO odds_snapshots (
        match_id, provider_id, bookmaker, market, selection, decimal_odds,
        observation_role, observation_origin, observation_source_kind,
        timing_semantics, quality_status, quality_reasons,
        source_staging_row_id, source_field, mapping_version,
        normalization_version, quality_policy_version, observed_at
    ) VALUES (
        :match_id, :provider_id, :bookmaker, 'match_result', 'home', :decimal_odds,
        :observation_role, :observation_origin, :observation_source_kind,
        :timing_semantics, :quality_status, :quality_reasons,
        :source_staging_row_id, :source_field, :mapping_version,
        :normalization_version, :quality_policy_version, :observed_at
    ) RETURNING odds_snapshot_id
"""


def _historical_parameters(context: Mapping[str, int]) -> dict[str, object]:
    return {
        **context,
        "bookmaker": "BET365",
        "decimal_odds": Decimal("2.10"),
        "observation_role": "source_final",
        "observation_origin": "historical_source",
        "observation_source_kind": "bookmaker",
        "timing_semantics": "role_only",
        "quality_status": "eligible",
        "quality_reasons": [],
        "source_field": "B365H",
        "mapping_version": "football_data_mapping_v1",
        "normalization_version": "historical_odds_normalization_v1",
        "quality_policy_version": "football_data_quality_v1",
        "observed_at": None,
    }


def test_controlled_domain_values_are_stable() -> None:
    assert tuple(ObservationOrigin) == (
        ObservationOrigin.HISTORICAL_SOURCE,
        ObservationOrigin.LIVE_SOURCE,
    )
    assert ObservationSourceKind.SOURCE_AVERAGE.value == "source_average"
    assert ObservationRole.SOURCE_FINAL.value == "source_final"
    assert TimingSemantics.ROLE_ONLY.value == "role_only"
    assert OddsQualityStatus.EXCLUDED.value == "excluded"


def test_schema_columns_and_nullability(db: Connection) -> None:
    rows = db.execute(
        text(
            """
            SELECT column_name, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='odds_snapshots'
            """
        )
    ).all()
    columns = {row.column_name: (row.is_nullable, row.data_type) for row in rows}
    assert columns["bookmaker"] == ("YES", "text")
    assert columns["observed_at"] == ("YES", "timestamp with time zone")
    assert columns["quality_reasons"] == ("NO", "ARRAY")
    for name in (
        "observation_origin",
        "observation_source_kind",
        "observation_role",
        "timing_semantics",
        "quality_status",
    ):
        assert columns[name][0] == "NO"
    assert "snapshot_at" not in columns
    assert "snapshot_type" not in columns


@pytest.mark.parametrize(
    ("source_kind", "bookmaker"),
    [("bookmaker", "BET365"), ("source_average", None), ("source_maximum", None)],
)
def test_valid_source_kind_bookmaker_combinations(
    db: Connection, source_kind: str, bookmaker: str | None
) -> None:
    context = _context(db)
    parameters = _historical_parameters(context)
    parameters.update(observation_source_kind=source_kind, bookmaker=bookmaker)
    assert _id(db, HISTORICAL_INSERT, parameters) > 0


@pytest.mark.parametrize(
    ("source_kind", "bookmaker"),
    [
        ("bookmaker", None),
        ("bookmaker", ""),
        ("source_average", "Average"),
        ("source_maximum", "Max"),
    ],
)
def test_invalid_source_kind_bookmaker_combinations(
    db: Connection, source_kind: str, bookmaker: str | None
) -> None:
    context = _context(db)
    parameters = _historical_parameters(context)
    parameters.update(observation_source_kind=source_kind, bookmaker=bookmaker)
    _reject(db, HISTORICAL_INSERT, parameters)


@pytest.mark.parametrize(
    ("timing", "observed_at"),
    [
        ("exact", datetime(2099, 1, 1, tzinfo=UTC)),
        ("role_only", None),
        ("unknown", None),
    ],
)
def test_valid_timing_semantics(db: Connection, timing: str, observed_at: datetime | None) -> None:
    context = _context(db)
    parameters = _historical_parameters(context)
    parameters.update(timing_semantics=timing, observed_at=observed_at)
    assert _id(db, HISTORICAL_INSERT, parameters) > 0


def test_exact_timing_requires_observed_at(db: Connection) -> None:
    context = _context(db)
    parameters = _historical_parameters(context)
    parameters.update(timing_semantics="exact", observed_at=None)
    _reject(db, HISTORICAL_INSERT, parameters)


@pytest.mark.parametrize(
    "missing_field",
    [
        "source_staging_row_id",
        "source_field",
        "mapping_version",
        "normalization_version",
        "quality_policy_version",
    ],
)
def test_historical_source_requires_complete_lineage(db: Connection, missing_field: str) -> None:
    context = _context(db)
    parameters = _historical_parameters(context)
    parameters[missing_field] = None
    _reject(db, HISTORICAL_INSERT, parameters)


@pytest.mark.parametrize(
    "version_field",
    ["source_field", "mapping_version", "normalization_version", "quality_policy_version"],
)
@pytest.mark.parametrize("blank", ["", "   "])
def test_historical_identifiers_must_be_nonblank(
    db: Connection, version_field: str, blank: str
) -> None:
    context = _context(db)
    parameters = _historical_parameters(context)
    parameters[version_field] = blank
    _reject(db, HISTORICAL_INSERT, parameters)


def test_live_source_does_not_require_football_data_lineage(db: Connection) -> None:
    context = _context(db)
    parameters = _historical_parameters(context)
    parameters.update(
        observation_origin="live_source",
        observation_role="live",
        timing_semantics="exact",
        observed_at=datetime(2099, 1, 1, tzinfo=UTC),
        source_staging_row_id=None,
        source_field=None,
        mapping_version=None,
        normalization_version=None,
        quality_policy_version=None,
    )
    assert _id(db, HISTORICAL_INSERT, parameters) > 0


def test_historical_identity_is_unique(db: Connection) -> None:
    parameters = _historical_parameters(_context(db))
    assert _id(db, HISTORICAL_INSERT, parameters) > 0
    _reject(db, HISTORICAL_INSERT, parameters)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_field", "B365D"),
        ("mapping_version", "football_data_mapping_v2"),
        ("normalization_version", "historical_odds_normalization_v2"),
        ("quality_policy_version", "football_data_quality_v2"),
    ],
)
def test_historical_identity_allows_versioned_reinterpretation(
    db: Connection, field: str, value: str
) -> None:
    parameters = _historical_parameters(_context(db))
    assert _id(db, HISTORICAL_INSERT, parameters) > 0
    changed = dict(parameters)
    changed[field] = value
    assert _id(db, HISTORICAL_INSERT, changed) > 0


@pytest.mark.parametrize("decimal_odds", [Decimal("1"), Decimal("0"), Decimal("-2")])
def test_existing_price_constraint_rejects_invalid_odds(
    db: Connection, decimal_odds: Decimal
) -> None:
    parameters = _historical_parameters(_context(db))
    parameters["decimal_odds"] = decimal_odds
    _reject(db, HISTORICAL_INSERT, parameters)


def test_existing_price_constraint_accepts_1_01(db: Connection) -> None:
    parameters = _historical_parameters(_context(db))
    parameters["decimal_odds"] = Decimal("1.01")
    assert _id(db, HISTORICAL_INSERT, parameters) > 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("observation_origin", "derived"),
        ("observation_source_kind", "consensus"),
        ("observation_role", "morning"),
        ("timing_semantics", "inferred"),
        ("quality_status", "unknown"),
    ],
)
def test_unsupported_controlled_values_are_rejected(db: Connection, field: str, value: str) -> None:
    parameters = _historical_parameters(_context(db))
    parameters[field] = value
    _reject(db, HISTORICAL_INSERT, parameters)


def test_quality_reasons_round_trip(db: Connection) -> None:
    parameters = _historical_parameters(_context(db))
    parameters["quality_status"] = "suspect"
    parameters["quality_reasons"] = [
        "timestamp_uncertain",
        "provider_quality_boundary",
    ]
    odds_id = _id(db, HISTORICAL_INSERT, parameters)
    reasons = db.execute(
        text("SELECT quality_reasons FROM odds_snapshots WHERE odds_snapshot_id=:odds_id"),
        {"odds_id": odds_id},
    ).scalar_one()
    assert reasons == ["timestamp_uncertain", "provider_quality_boundary"]


def test_staging_lineage_uses_restrict(db: Connection) -> None:
    context = _context(db)
    assert _id(db, HISTORICAL_INSERT, _historical_parameters(context)) > 0
    _reject(
        db,
        "DELETE FROM football_data_staging_rows WHERE staging_row_id=:staging_row_id",
        {"staging_row_id": context["source_staging_row_id"]},
    )


def test_historical_unique_index_is_partial(db: Connection) -> None:
    definition = db.execute(
        text(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public' AND tablename='odds_snapshots'
              AND indexname='uq_odds_historical_source_identity'
            """
        )
    ).scalar_one()
    assert "UNIQUE INDEX" in definition
    assert "WHERE (observation_origin = 'historical_source'::text)" in definition
