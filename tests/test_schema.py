from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.config import load_settings


@pytest.fixture(scope="session")
def database_engine() -> Iterator[Engine]:
    settings = load_settings(os.environ)
    engine = create_engine(settings.database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(database_engine: Engine) -> Iterator[Connection]:
    with database_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _id(
    db: Connection,
    statement: str,
    parameters: Mapping[str, object] | None = None,
) -> int:
    value = db.execute(text(statement), parameters or {}).scalar_one()
    assert isinstance(value, int)
    return value


def _reject(
    db: Connection,
    statement: str,
    parameters: Mapping[str, object] | None = None,
) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text(statement), parameters or {})


def _provider(db: Connection, name: str = "Test Provider") -> int:
    return _id(
        db,
        """
        INSERT INTO providers (name, provider_type, priority)
        VALUES (:name, 'football_data', 1)
        RETURNING provider_id
        """,
        {"name": name},
    )


def _competition(db: Connection, name: str = "Test Competition") -> int:
    return _id(
        db,
        """
        INSERT INTO competitions (canonical_name, country_code, competition_type)
        VALUES (:name, 'TST', 'domestic_league')
        RETURNING competition_id
        """,
        {"name": name},
    )


def _season(db: Connection, competition_id: int, name: str = "2099/00") -> int:
    return _id(
        db,
        """
        INSERT INTO seasons (
            competition_id, season_name, start_year, end_year, status
        ) VALUES (:competition_id, :name, 2099, 2100, 'planned')
        RETURNING season_id
        """,
        {"competition_id": competition_id, "name": name},
    )


def _team(db: Connection, name: str) -> int:
    return _id(
        db,
        """
        INSERT INTO teams (canonical_name, normalized_name, country_code)
        VALUES (:name, :normalized_name, 'TST')
        RETURNING team_id
        """,
        {"name": name, "normalized_name": name.casefold()},
    )


def _match(
    db: Connection,
    competition_id: int,
    season_id: int,
    home_team_id: int,
    away_team_id: int,
) -> int:
    return _id(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (
            :competition_id, :season_id, :home_team_id, :away_team_id, 'SCHEDULED'
        )
        RETURNING match_id
        """,
        {
            "competition_id": competition_id,
            "season_id": season_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        },
    )


def _match_context(db: Connection) -> dict[str, int]:
    competition_id = _competition(db)
    season_id = _season(db, competition_id)
    home_team_id = _team(db, "Home Test FC")
    away_team_id = _team(db, "Away Test FC")
    match_id = _match(db, competition_id, season_id, home_team_id, away_team_id)
    return {
        "competition_id": competition_id,
        "season_id": season_id,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "match_id": match_id,
    }


def _insert_odds(
    db: Connection,
    match_id: int,
    decimal_odds: Decimal,
    line: Decimal | None = None,
) -> int:
    return _id(
        db,
        """
        INSERT INTO odds_snapshots (
            match_id, bookmaker, market, selection, line, decimal_odds, snapshot_type
        ) VALUES (
            :match_id, 'Test Book', 'match_result', 'home', :line, :decimal_odds, 'opening'
        )
        RETURNING odds_snapshot_id
        """,
        {"match_id": match_id, "line": line, "decimal_odds": decimal_odds},
    )


@pytest.mark.integration
def test_duplicate_provider_name_is_rejected(db: Connection) -> None:
    _provider(db)
    _reject(
        db,
        "INSERT INTO providers (name, provider_type, priority) VALUES ('Test Provider', 'odds', 2)",
    )


@pytest.mark.integration
def test_duplicate_competition_season_name_is_rejected(db: Connection) -> None:
    competition_id = _competition(db)
    _season(db, competition_id)
    _reject(
        db,
        """
        INSERT INTO seasons (competition_id, season_name, start_year, end_year, status)
        VALUES (:competition_id, '2099/00', 2099, 2100, 'planned')
        """,
        {"competition_id": competition_id},
    )


@pytest.mark.integration
def test_match_with_same_home_and_away_team_is_rejected(db: Connection) -> None:
    competition_id = _competition(db)
    season_id = _season(db, competition_id)
    team_id = _team(db, "Only Test FC")
    _reject(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (:competition_id, :season_id, :team_id, :team_id, 'SCHEDULED')
        """,
        {"competition_id": competition_id, "season_id": season_id, "team_id": team_id},
    )


@pytest.mark.integration
def test_negative_match_score_is_rejected(db: Connection) -> None:
    context = _match_context(db)
    _reject(
        db,
        "UPDATE matches SET home_score = -1, away_score = 0 WHERE match_id = :match_id",
        {"match_id": context["match_id"]},
    )


@pytest.mark.integration
@pytest.mark.parametrize("decimal_odds", [Decimal("1.0"), Decimal("0.9999")])
def test_odds_not_greater_than_one_are_rejected(db: Connection, decimal_odds: Decimal) -> None:
    context = _match_context(db)
    _reject(
        db,
        """
        INSERT INTO odds_snapshots (
            match_id, bookmaker, market, selection, decimal_odds, snapshot_type
        ) VALUES (
            :match_id, 'Test Book', 'match_result', 'home', :decimal_odds, 'opening'
        )
        """,
        {"match_id": context["match_id"], "decimal_odds": decimal_odds},
    )


@pytest.mark.integration
def test_odds_greater_than_one_are_accepted(db: Connection) -> None:
    context = _match_context(db)
    assert _insert_odds(db, context["match_id"], Decimal("1.0001")) > 0


@pytest.mark.integration
def test_provider_match_id_is_unique_within_provider(db: Connection) -> None:
    context = _match_context(db)
    provider_id = _provider(db)
    second_match_id = _match(
        db,
        context["competition_id"],
        context["season_id"],
        context["away_team_id"],
        context["home_team_id"],
    )
    db.execute(
        text(
            """
            INSERT INTO match_provider_refs (match_id, provider_id, provider_match_id)
            VALUES (:match_id, :provider_id, 'external-match-1')
            """
        ),
        {"match_id": context["match_id"], "provider_id": provider_id},
    )
    _reject(
        db,
        """
        INSERT INTO match_provider_refs (match_id, provider_id, provider_match_id)
        VALUES (:match_id, :provider_id, 'external-match-1')
        """,
        {"match_id": second_match_id, "provider_id": provider_id},
    )


@pytest.mark.integration
def test_provider_team_id_is_unique_within_provider(db: Connection) -> None:
    provider_id = _provider(db)
    first_team_id = _team(db, "First Test FC")
    second_team_id = _team(db, "Second Test FC")
    db.execute(
        text(
            """
            INSERT INTO team_aliases (
                team_id, provider_id, alias, normalized_alias, provider_team_id
            ) VALUES (:team_id, :provider_id, 'First', 'first', 'external-team-1')
            """
        ),
        {"team_id": first_team_id, "provider_id": provider_id},
    )
    _reject(
        db,
        """
        INSERT INTO team_aliases (
            team_id, provider_id, alias, normalized_alias, provider_team_id
        ) VALUES (:team_id, :provider_id, 'Second', 'second', 'external-team-1')
        """,
        {"team_id": second_team_id, "provider_id": provider_id},
    )


@pytest.mark.integration
def test_null_statistics_are_accepted(db: Connection) -> None:
    context = _match_context(db)
    statistics_id = _id(
        db,
        "INSERT INTO match_statistics (match_id) VALUES (:match_id) RETURNING match_statistics_id",
        {"match_id": context["match_id"]},
    )
    assert statistics_id > 0


@pytest.mark.integration
def test_null_statistics_do_not_default_to_zero(db: Connection) -> None:
    context = _match_context(db)
    row = db.execute(
        text(
            """
            INSERT INTO match_statistics (match_id)
            VALUES (:match_id)
            RETURNING home_shots, home_corners, home_possession, home_xg,
                      away_shots, away_corners, away_possession, away_xg
            """
        ),
        {"match_id": context["match_id"]},
    ).one()
    assert all(value is None for value in row)


@pytest.mark.integration
@pytest.mark.parametrize(
    "column",
    [
        "home_shots",
        "home_shots_on_target",
        "home_corners",
        "home_fouls",
        "home_yellow_cards",
        "home_red_cards",
        "away_shots",
        "away_corners",
        "away_yellow_cards",
    ],
)
def test_negative_count_statistics_are_rejected(db: Connection, column: str) -> None:
    context = _match_context(db)
    allowed_columns = {
        "home_shots",
        "home_shots_on_target",
        "home_corners",
        "home_fouls",
        "home_yellow_cards",
        "home_red_cards",
        "away_shots",
        "away_corners",
        "away_yellow_cards",
    }
    assert column in allowed_columns
    _reject(
        db,
        f"INSERT INTO match_statistics (match_id, {column}) VALUES (:match_id, -1)",
        {"match_id": context["match_id"]},
    )


@pytest.mark.integration
@pytest.mark.parametrize("possession", [Decimal("-0.01"), Decimal("100.01")])
def test_possession_outside_zero_to_one_hundred_is_rejected(
    db: Connection, possession: Decimal
) -> None:
    context = _match_context(db)
    _reject(
        db,
        """
        INSERT INTO match_statistics (match_id, home_possession)
        VALUES (:match_id, :possession)
        """,
        {"match_id": context["match_id"], "possession": possession},
    )


@pytest.mark.integration
def test_negative_xg_is_rejected(db: Connection) -> None:
    context = _match_context(db)
    _reject(
        db,
        "INSERT INTO match_statistics (match_id, home_xg) VALUES (:match_id, -0.001)",
        {"match_id": context["match_id"]},
    )


@pytest.mark.integration
@pytest.mark.parametrize("team_column", ["home_team_id", "away_team_id"])
def test_match_cannot_reference_nonexistent_team(db: Connection, team_column: str) -> None:
    context = _match_context(db)
    assert team_column in {"home_team_id", "away_team_id"}
    _reject(
        db,
        f"UPDATE matches SET {team_column} = 9223372036854770000 WHERE match_id = :match_id",
        {"match_id": context["match_id"]},
    )


@pytest.mark.integration
def test_orphan_season_is_rejected(db: Connection) -> None:
    _reject(
        db,
        """
        INSERT INTO seasons (competition_id, season_name, start_year, end_year, status)
        VALUES (9223372036854770000, '2099/00', 2099, 2100, 'planned')
        """,
    )


@pytest.mark.integration
def test_orphan_odds_are_rejected(db: Connection) -> None:
    _reject(
        db,
        """
        INSERT INTO odds_snapshots (
            match_id, bookmaker, market, selection, decimal_odds, snapshot_type
        ) VALUES (
            9223372036854770000, 'Test Book', 'match_result', 'home', 2.0, 'opening'
        )
        """,
    )


@pytest.mark.integration
def test_orphan_statistics_are_rejected(db: Connection) -> None:
    _reject(
        db,
        "INSERT INTO match_statistics (match_id) VALUES (9223372036854770000)",
    )


@pytest.mark.integration
def test_team_alias_invalid_date_range_is_rejected(db: Connection) -> None:
    team_id = _team(db, "Date Test FC")
    _reject(
        db,
        """
        INSERT INTO team_aliases (
            team_id, alias, normalized_alias, valid_from, valid_to
        ) VALUES (:team_id, 'Date Test', 'date test', '2026-09-02', '2026-09-01')
        """,
        {"team_id": team_id},
    )


@pytest.mark.integration
def test_import_batch_completion_before_start_is_rejected(db: Connection) -> None:
    provider_id = _provider(db)
    _reject(
        db,
        """
        INSERT INTO import_batches (
            provider_id, started_at, completed_at, source_identifier, status
        ) VALUES (
            :provider_id, '2026-09-02T00:00:00Z', '2026-09-01T00:00:00Z',
            'test-source', 'failed'
        )
        """,
        {"provider_id": provider_id},
    )


@pytest.mark.integration
def test_match_season_competition_mismatch_is_rejected(db: Connection) -> None:
    competition_a = _competition(db, "Competition A")
    competition_b = _competition(db, "Competition B")
    season_a = _season(db, competition_a)
    home_team_id = _team(db, "Mismatch Home FC")
    away_team_id = _team(db, "Mismatch Away FC")
    _reject(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (
            :competition_b, :season_a, :home_team_id, :away_team_id, 'SCHEDULED'
        )
        """,
        {
            "competition_b": competition_b,
            "season_a": season_a,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        },
    )


@pytest.mark.integration
def test_provider_team_id_without_provider_is_rejected(db: Connection) -> None:
    team_id = _team(db, "Context Test FC")
    _reject(
        db,
        """
        INSERT INTO team_aliases (team_id, alias, normalized_alias, provider_team_id)
        VALUES (:team_id, 'Context Test', 'context test', 'external-team-1')
        """,
        {"team_id": team_id},
    )


@pytest.mark.integration
@pytest.mark.parametrize("provider_id", [None, 9223372036854770000])
def test_provider_competition_id_requires_valid_provider_context(
    db: Connection, provider_id: int | None
) -> None:
    competition_id = _competition(db)
    _reject(
        db,
        """
        INSERT INTO competition_provider_refs (
            competition_id, provider_id, provider_competition_id
        ) VALUES (:competition_id, :provider_id, 'external-competition-1')
        """,
        {"competition_id": competition_id, "provider_id": provider_id},
    )


@pytest.mark.integration
def test_same_provider_match_id_is_allowed_under_different_providers(db: Connection) -> None:
    context = _match_context(db)
    provider_a = _provider(db, "Provider A")
    provider_b = _provider(db, "Provider B")
    for provider_id in (provider_a, provider_b):
        db.execute(
            text(
                """
                INSERT INTO match_provider_refs (match_id, provider_id, provider_match_id)
                VALUES (:match_id, :provider_id, 'shared-external-id')
                """
            ),
            {"match_id": context["match_id"], "provider_id": provider_id},
        )


@pytest.mark.integration
def test_duplicate_match_provider_statistics_are_rejected(db: Connection) -> None:
    context = _match_context(db)
    provider_id = _provider(db)
    parameters = {"match_id": context["match_id"], "provider_id": provider_id}
    statement = """
        INSERT INTO match_statistics (match_id, provider_id)
        VALUES (:match_id, :provider_id)
    """
    db.execute(text(statement), parameters)
    _reject(db, statement, parameters)


@pytest.mark.integration
def test_only_one_providerless_statistics_row_is_allowed(db: Connection) -> None:
    context = _match_context(db)
    statement = "INSERT INTO match_statistics (match_id) VALUES (:match_id)"
    parameters = {"match_id": context["match_id"]}
    db.execute(text(statement), parameters)
    _reject(db, statement, parameters)


@pytest.mark.integration
def test_null_statistics_survive_insert_read_roundtrip(db: Connection) -> None:
    context = _match_context(db)
    db.execute(
        text("INSERT INTO match_statistics (match_id) VALUES (:match_id)"),
        {"match_id": context["match_id"]},
    )
    row = db.execute(
        text(
            """
            SELECT home_shots, home_possession, home_xg,
                   away_shots, away_possession, away_xg
            FROM match_statistics
            WHERE match_id = :match_id
            """
        ),
        {"match_id": context["match_id"]},
    ).one()
    assert tuple(row) == (None, None, None, None, None, None)


@pytest.mark.integration
def test_odds_line_may_be_null(db: Connection) -> None:
    context = _match_context(db)
    odds_id = _insert_odds(db, context["match_id"], Decimal("2.0000"), None)
    line = db.execute(
        text("SELECT line FROM odds_snapshots WHERE odds_snapshot_id = :odds_id"),
        {"odds_id": odds_id},
    ).scalar_one()
    assert line is None


@pytest.mark.integration
def test_decimal_odds_survive_exact_roundtrip(db: Connection) -> None:
    context = _match_context(db)
    expected = Decimal("2.3456")
    odds_id = _insert_odds(db, context["match_id"], expected)
    actual = db.execute(
        text("SELECT decimal_odds FROM odds_snapshots WHERE odds_snapshot_id = :odds_id"),
        {"odds_id": odds_id},
    ).scalar_one()
    assert actual == expected


@pytest.mark.integration
def test_match_delete_is_restricted_when_historical_child_exists(db: Connection) -> None:
    context = _match_context(db)
    _insert_odds(db, context["match_id"], Decimal("2.0000"))
    _reject(
        db,
        "DELETE FROM matches WHERE match_id = :match_id",
        {"match_id": context["match_id"]},
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM matches WHERE match_id = :match_id"),
            {"match_id": context["match_id"]},
        ).scalar_one()
        == 1
    )


@pytest.mark.integration
def test_ten_v1_competitions_are_seeded(db: Connection) -> None:
    expected = {
        "Premier League",
        "Ligue 1",
        "Bundesliga",
        "Süper Lig",
        "Primeira Liga",
        "La Liga",
        "Scottish Premiership",
        "UEFA Champions League",
        "UEFA Europa League",
        "UEFA Conference League",
    }
    actual = set(
        db.execute(
            text("SELECT canonical_name FROM competitions WHERE canonical_name = ANY(:names)"),
            {"names": list(expected)},
        ).scalars()
    )
    assert actual == expected


@pytest.mark.integration
def test_required_canonical_tables_exist(db: Connection) -> None:
    expected = {
        "providers",
        "competitions",
        "competition_provider_refs",
        "seasons",
        "teams",
        "team_aliases",
        "matches",
        "match_provider_refs",
        "match_statistics",
        "odds_snapshots",
        "data_quality",
        "import_batches",
    }
    actual = set(
        db.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = ANY(:names)
                """
            ),
            {"names": list(expected)},
        ).scalars()
    )
    assert actual == expected
