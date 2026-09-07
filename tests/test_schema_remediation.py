from __future__ import annotations

import os
from collections.abc import Iterator, Mapping

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.config import load_settings


@pytest.fixture(scope="session")
def remediation_engine() -> Iterator[Engine]:
    settings = load_settings(os.environ)
    engine = create_engine(settings.database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(remediation_engine: Engine) -> Iterator[Connection]:
    with remediation_engine.connect() as connection:
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


def _provider(db: Connection) -> int:
    return _id(
        db,
        """
        INSERT INTO providers (name, provider_type, priority)
        VALUES ('Remediation Provider', 'football_data', 1)
        RETURNING provider_id
        """,
    )


def _context(db: Connection) -> dict[str, int]:
    competition_id = _id(
        db,
        """
        INSERT INTO competitions (
            canonical_name, country_code, jurisdiction_code, competition_type
        ) VALUES ('Remediation Competition', 'FRA', 'FRA', 'domestic_league')
        RETURNING competition_id
        """,
    )
    season_id = _id(
        db,
        """
        INSERT INTO seasons (
            competition_id, season_name, start_year, end_year, status
        ) VALUES (:competition_id, '2099/00', 2099, 2100, 'planned')
        RETURNING season_id
        """,
        {"competition_id": competition_id},
    )
    home_team_id = _id(
        db,
        """
        INSERT INTO teams (canonical_name, normalized_name, country_code)
        VALUES ('Remediation Home FC', 'remediation home fc', 'FRA')
        RETURNING team_id
        """,
    )
    away_team_id = _id(
        db,
        """
        INSERT INTO teams (canonical_name, normalized_name, country_code)
        VALUES ('Remediation Away FC', 'remediation away fc', 'FRA')
        RETURNING team_id
        """,
    )
    return {
        "competition_id": competition_id,
        "season_id": season_id,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
    }


def _insert_scored_match(
    db: Connection,
    *,
    home_score: int,
    away_score: int,
    result: str,
    status: str = "FINISHED",
    extra_time: tuple[int, int] | None = None,
    penalties: tuple[int, int] | None = None,
    decided_by: str = "regular_time",
    score_is_awarded: bool = False,
) -> int:
    context = _context(db)
    return _id(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status,
            home_score, away_score, result,
            home_extra_time_score, away_extra_time_score,
            home_penalty_score, away_penalty_score,
            decided_by, score_is_awarded
        ) VALUES (
            :competition_id, :season_id, :home_team_id, :away_team_id, :status,
            :home_score, :away_score, :result,
            :home_extra_time_score, :away_extra_time_score,
            :home_penalty_score, :away_penalty_score,
            :decided_by, :score_is_awarded
        )
        RETURNING match_id
        """,
        {
            **context,
            "status": status,
            "home_score": home_score,
            "away_score": away_score,
            "result": result,
            "home_extra_time_score": None if extra_time is None else extra_time[0],
            "away_extra_time_score": None if extra_time is None else extra_time[1],
            "home_penalty_score": None if penalties is None else penalties[0],
            "away_penalty_score": None if penalties is None else penalties[1],
            "decided_by": decided_by,
            "score_is_awarded": score_is_awarded,
        },
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("competition", "country_code", "jurisdiction_code"),
    [
        ("Premier League", "GBR", "ENG"),
        ("Ligue 1", "FRA", "FRA"),
        ("Bundesliga", "DEU", "DEU"),
        ("Süper Lig", "TUR", "TUR"),
        ("Primeira Liga", "PRT", "PRT"),
        ("La Liga", "ESP", "ESP"),
        ("Scottish Premiership", "GBR", "SCO"),
        ("UEFA Champions League", None, "UEFA"),
        ("UEFA Europa League", None, "UEFA"),
        ("UEFA Conference League", None, "UEFA"),
    ],
)
def test_seed_country_and_jurisdiction_semantics(
    db: Connection,
    competition: str,
    country_code: str | None,
    jurisdiction_code: str,
) -> None:
    row = db.execute(
        text(
            """
            SELECT country_code, jurisdiction_code
            FROM competitions
            WHERE canonical_name = :competition AND gender = 'men'
            """
        ),
        {"competition": competition},
    ).one()
    assert tuple(row) == (country_code, jurisdiction_code)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("home_score", "away_score", "result"),
    [(2, 1, "H"), (1, 1, "D"), (0, 1, "A")],
)
def test_consistent_finished_result_is_accepted(
    db: Connection, home_score: int, away_score: int, result: str
) -> None:
    assert _insert_scored_match(db, home_score=home_score, away_score=away_score, result=result) > 0


@pytest.mark.integration
@pytest.mark.parametrize(
    ("home_score", "away_score", "result"),
    [(2, 1, "D"), (1, 1, "H"), (0, 1, "H"), (0, 1, "D")],
)
def test_contradictory_finished_result_is_rejected(
    db: Connection, home_score: int, away_score: int, result: str
) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        _insert_scored_match(db, home_score=home_score, away_score=away_score, result=result)


@pytest.mark.integration
def test_extra_time_does_not_change_normal_time_result(db: Connection) -> None:
    match_id = _insert_scored_match(
        db,
        home_score=1,
        away_score=1,
        result="D",
        extra_time=(2, 1),
        decided_by="extra_time",
    )
    row = db.execute(
        text(
            """
            SELECT home_score, away_score, result,
                   home_extra_time_score, away_extra_time_score, decided_by
            FROM matches WHERE match_id = :match_id
            """
        ),
        {"match_id": match_id},
    ).one()
    assert tuple(row) == (1, 1, "D", 2, 1, "extra_time")


@pytest.mark.integration
def test_penalties_do_not_change_normal_time_result(db: Connection) -> None:
    match_id = _insert_scored_match(
        db,
        home_score=1,
        away_score=1,
        result="D",
        penalties=(4, 3),
        decided_by="penalties",
    )
    row = db.execute(
        text(
            """
            SELECT home_score, away_score, result,
                   home_penalty_score, away_penalty_score, decided_by
            FROM matches WHERE match_id = :match_id
            """
        ),
        {"match_id": match_id},
    ).one()
    assert tuple(row) == (1, 1, "D", 4, 3, "penalties")


@pytest.mark.integration
def test_awarded_result_may_differ_from_score_comparison(db: Connection) -> None:
    match_id = _insert_scored_match(
        db,
        home_score=3,
        away_score=0,
        result="A",
        status="AWARDED",
        decided_by="awarded",
        score_is_awarded=True,
    )
    assert match_id > 0


@pytest.mark.integration
def test_provider_market_id_without_provider_is_rejected(db: Connection) -> None:
    context = _context(db)
    match_id = _id(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (
            :competition_id, :season_id, :home_team_id, :away_team_id, 'SCHEDULED'
        ) RETURNING match_id
        """,
        context,
    )
    _reject(
        db,
        """
        INSERT INTO odds_snapshots (
            match_id, bookmaker, market, selection, decimal_odds,
            snapshot_type, provider_market_id
        ) VALUES (
            :match_id, 'Test Book', 'match_result', 'home', 2.0,
            'opening', 'market-1'
        )
        """,
        {"match_id": match_id},
    )


@pytest.mark.integration
def test_provider_market_id_with_provider_is_accepted(db: Connection) -> None:
    context = _context(db)
    provider_id = _provider(db)
    match_id = _id(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (
            :competition_id, :season_id, :home_team_id, :away_team_id, 'SCHEDULED'
        ) RETURNING match_id
        """,
        context,
    )
    odds_id = _id(
        db,
        """
        INSERT INTO odds_snapshots (
            match_id, provider_id, bookmaker, market, selection, decimal_odds,
            snapshot_type, provider_market_id
        ) VALUES (
            :match_id, :provider_id, 'Test Book', 'match_result', 'home', 2.0,
            'opening', 'market-1'
        ) RETURNING odds_snapshot_id
        """,
        {"match_id": match_id, "provider_id": provider_id},
    )
    assert odds_id > 0


@pytest.mark.integration
def test_null_provider_market_and_provider_are_accepted(db: Connection) -> None:
    context = _context(db)
    match_id = _id(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (
            :competition_id, :season_id, :home_team_id, :away_team_id, 'SCHEDULED'
        ) RETURNING match_id
        """,
        context,
    )
    odds_id = _id(
        db,
        """
        INSERT INTO odds_snapshots (
            match_id, bookmaker, market, selection, decimal_odds, snapshot_type
        ) VALUES (
            :match_id, 'Test Book', 'match_result', 'home', 2.0, 'opening'
        ) RETURNING odds_snapshot_id
        """,
        {"match_id": match_id},
    )
    assert odds_id > 0


def _external_id_statement(
    kind: str,
    context: Mapping[str, int],
    provider_id: int,
) -> tuple[str, dict[str, object]]:
    if kind == "competition":
        return (
            """
            INSERT INTO competition_provider_refs (
                competition_id, provider_id, provider_competition_id, provider_name
            ) VALUES (:competition_id, :provider_id, :external_id, 'Provider Competition')
            """,
            {
                "competition_id": context["competition_id"],
                "provider_id": provider_id,
            },
        )
    if kind == "team":
        return (
            """
            INSERT INTO team_aliases (
                team_id, provider_id, alias, normalized_alias, provider_team_id
            ) VALUES (
                :home_team_id, :provider_id, 'Provider Team',
                'provider team', :external_id
            )
            """,
            {"home_team_id": context["home_team_id"], "provider_id": provider_id},
        )
    if kind == "match":
        return (
            """
            INSERT INTO match_provider_refs (match_id, provider_id, provider_match_id)
            VALUES (:match_id, :provider_id, :external_id)
            """,
            {"match_id": context["match_id"], "provider_id": provider_id},
        )
    assert kind == "market"
    return (
        """
        INSERT INTO odds_snapshots (
            match_id, provider_id, bookmaker, market, selection, decimal_odds,
            snapshot_type, provider_market_id
        ) VALUES (
            :match_id, :provider_id, 'Test Book', 'match_result', 'home', 2.0,
            'opening', :external_id
        )
        """,
        {"match_id": context["match_id"], "provider_id": provider_id},
    )


def _external_id_context(db: Connection) -> tuple[dict[str, int], int]:
    context = _context(db)
    context["match_id"] = _id(
        db,
        """
        INSERT INTO matches (
            competition_id, season_id, home_team_id, away_team_id, status
        ) VALUES (
            :competition_id, :season_id, :home_team_id, :away_team_id, 'SCHEDULED'
        ) RETURNING match_id
        """,
        context,
    )
    return context, _provider(db)


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["competition", "team", "match", "market"])
@pytest.mark.parametrize("blank_value", ["", "   "])
def test_blank_external_identifier_is_rejected(db: Connection, kind: str, blank_value: str) -> None:
    context, provider_id = _external_id_context(db)
    statement, parameters = _external_id_statement(kind, context, provider_id)
    parameters["external_id"] = blank_value
    _reject(db, statement, parameters)


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["competition", "team", "match", "market"])
def test_null_external_identifier_remains_accepted(db: Connection, kind: str) -> None:
    context, provider_id = _external_id_context(db)
    statement, parameters = _external_id_statement(kind, context, provider_id)
    parameters["external_id"] = None
    db.execute(text(statement), parameters)
