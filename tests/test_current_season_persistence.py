# ruff: noqa: E501
from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

import pitchvalue.operations.current_season as current_season
from pitchvalue.config import load_settings
from pitchvalue.operations.current_season import (
    deterministic_run_id,
    persist_current_season_payloads,
)
from pitchvalue.operations.shadow_repository import ShadowAnalysisWrite, persist_shadow_analysis
from pitchvalue.providers.source_persistence import assign_team_reference

NOW = datetime(2026, 9, 13, tzinfo=UTC)


@pytest.fixture(scope="session")
def database_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(database_engine: Engine) -> Iterator[Connection]:
    with database_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _payload(
    *,
    fixture_id: int = 900001,
    home_id: int = 910001,
    away_id: int = 910002,
    home: str = "Persistence Home",
    away: str = "Persistence Away",
    kickoff: datetime = NOW + timedelta(days=1),
    status: str = "scheduled",
    goals: dict[str, int] | None = None,
    corners: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "id": fixture_id,
        "kickoff_utc": kickoff.isoformat(),
        "status": status,
        "goals": goals,
        "league": {"id": 100, "name": "Germany Bundesliga I"},
        "teams": {
            "home": {"id": home_id, "name": home},
            "away": {"id": away_id, "name": away},
        },
        "corners": corners,
    }


def _teams(db: Connection) -> tuple[int, int]:
    values = []
    for name in ("Persistence Home", "Persistence Away"):
        values.append(
            int(
                db.execute(
                    text(
                        """INSERT INTO teams (canonical_name,normalized_name,country_code)
                        VALUES (:name,:normalized,'DEU') RETURNING team_id"""
                    ),
                    {"name": name, "normalized": name.casefold()},
                ).scalar_one()
            )
        )
    return values[0], values[1]


@pytest.mark.integration
def test_current_fixture_and_source_replay_are_idempotent(db: Connection) -> None:
    _teams(db)
    payload = _payload(corners={"home": 0, "away": 4})
    run_id = deterministic_run_id((payload,), NOW)
    first = persist_current_season_payloads(
        db,
        (payload,),
        logical_run_id=run_id,
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    second = persist_current_season_payloads(
        db,
        (payload,),
        logical_run_id=run_id,
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert first.fixture_writes[0].status.value == "INSERTED"
    assert second.fixture_writes[0].status.value == "UNCHANGED"
    assert first.match_ids == second.match_ids
    assert (
        db.execute(
            text("SELECT count(*) FROM engine_runs WHERE logical_run_id=:id"), {"id": run_id}
        ).scalar_one()
        == 2
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM matches WHERE match_id=:id"), {"id": first.match_ids[0][1]}
        ).scalar_one()
        == 1
    )
    stats = db.execute(
        text("SELECT home_corners,away_corners FROM match_statistics WHERE match_id=:id"),
        {"id": first.match_ids[0][1]},
    ).one()
    assert tuple(stats) == (0, 4)


@pytest.mark.integration
def test_unresolved_team_is_persisted_for_explicit_review(db: Connection) -> None:
    payload = _payload(home="Unknown Provider Club", away="Another Unknown Club")
    result = persist_current_season_payloads(
        db,
        (payload,),
        logical_run_id=deterministic_run_id((payload,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert result.match_ids == ()
    assert result.quarantines_created == 1
    rows = (
        db.execute(
            text(
                """SELECT mapping_status FROM source_entity_references
                    WHERE entity_type='TEAM'
                      AND provider_entity_id IN ('910001','910002')
                    ORDER BY provider_entity_id"""
            )
        )
        .scalars()
        .all()
    )
    assert rows == ["UNRESOLVED", "UNRESOLVED"]


@pytest.mark.integration
def test_operator_can_explicitly_assign_unresolved_team(db: Connection) -> None:
    team_id = int(
        db.execute(
            text(
                """INSERT INTO teams (canonical_name,normalized_name)
                VALUES ('Review FC','review fc') RETURNING team_id"""
            )
        ).scalar_one()
    )
    payload = _payload(home="Unknown Provider Club", away="Another Unknown Club")
    result = persist_current_season_payloads(
        db,
        (payload,),
        logical_run_id=deterministic_run_id((payload,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    provider_id = result.provider_id
    reference_id = int(
        db.execute(
            text(
                """SELECT source_entity_ref_id FROM source_entity_references
                WHERE provider_id=:provider AND entity_type='TEAM'
                  AND provider_entity_id='910001'"""
            ),
            {"provider": provider_id},
        ).scalar_one()
    )
    assign_team_reference(db, reference_id, team_id, mapping_version="operator_review_v1")
    row = db.execute(
        text(
            """SELECT mapping_status,canonical_team_id FROM source_entity_references
            WHERE source_entity_ref_id=:id"""
        ),
        {"id": reference_id},
    ).one()
    assert tuple(row) == ("RESOLVED", team_id)


@pytest.mark.integration
def test_kickoff_revision_and_final_replay_are_safe(db: Connection) -> None:
    _teams(db)
    initial = _payload()
    run = deterministic_run_id((initial,), NOW)
    first = persist_current_season_payloads(
        db,
        (initial,),
        logical_run_id=run,
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    revised = _payload(kickoff=NOW + timedelta(days=1, hours=2))
    changed = persist_current_season_payloads(
        db,
        (revised,),
        logical_run_id=deterministic_run_id((revised,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert changed.fixture_writes[0].status.value == "KICKOFF_REVISED"
    finished = _payload(
        kickoff=NOW + timedelta(days=1, hours=2), status="finished", goals={"home": 2, "away": 1}
    )
    done = persist_current_season_payloads(
        db,
        (finished,),
        logical_run_id=deterministic_run_id((finished,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    replay = persist_current_season_payloads(
        db,
        (finished,),
        logical_run_id=deterministic_run_id((finished,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert done.fixture_writes[0].status.value == "FINISHED"
    assert replay.fixture_writes[0].status.value == "UNCHANGED"
    match_id = first.match_ids[0][1]
    assert tuple(
        db.execute(
            text("SELECT home_score,away_score,result FROM matches WHERE match_id=:id"),
            {"id": match_id},
        ).one()
    ) == (2, 1, "H")


@pytest.mark.integration
def test_final_result_correction_and_finished_kickoff_revision_require_review(
    db: Connection,
) -> None:
    _teams(db)
    finished = _payload(status="finished", goals={"home": 2, "away": 1})
    first = persist_current_season_payloads(
        db,
        (finished,),
        logical_run_id=deterministic_run_id((finished,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    corrected = _payload(status="finished", goals={"home": 1, "away": 1})
    correction = persist_current_season_payloads(
        db,
        (corrected,),
        logical_run_id=deterministic_run_id((corrected,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    moved_final = _payload(
        kickoff=NOW + timedelta(days=1, hours=2),
        status="finished",
        goals={"home": 2, "away": 1},
    )
    moved = persist_current_season_payloads(
        db,
        (moved_final,),
        logical_run_id=deterministic_run_id((moved_final,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert correction.fixture_writes[0].status.value == "RESULT_REVISION_REVIEW"
    assert moved.fixture_writes[0].status.value == "LIFECYCLE_REVIEW"
    match_id = first.match_ids[0][1]
    assert tuple(
        db.execute(
            text(
                "SELECT kickoff_at_utc,home_score,away_score,result FROM matches WHERE match_id=:id"
            ),
            {"id": match_id},
        ).one()
    ) == (NOW + timedelta(days=1), 2, 1, "H")


@pytest.mark.integration
def test_unknown_provider_lifecycle_is_quarantined_not_persisted(db: Connection) -> None:
    _teams(db)
    unknown = _payload(status="unknown")
    result = persist_current_season_payloads(
        db,
        (unknown,),
        logical_run_id=deterministic_run_id((unknown,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert result.fixture_writes == ()
    assert result.quarantines_created == 1
    assert result.terminal_status.value == "PARTIAL_WITH_QUARANTINES"
    assert result.match_ids == ()


@pytest.mark.integration
def test_shadow_analysis_is_idempotent_and_never_public(db: Connection) -> None:
    _teams(db)
    payload = _payload()
    run_id = deterministic_run_id((payload,), NOW)
    sync = persist_current_season_payloads(
        db,
        (payload,),
        logical_run_id=run_id,
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    actual_run_id = db.execute(
        text(
            "SELECT run_id FROM engine_runs WHERE logical_run_id = :id ORDER BY attempt_number DESC LIMIT 1"
        ),
        {"id": run_id},
    ).scalar_one()
    write = ShadowAnalysisWrite(
        actual_run_id,
        run_id,
        sync.match_ids[0][1],
        NOW,
        "raw_ml_v1",
        "features_v1",
        {"HOME": Decimal("0.4"), "DRAW": Decimal("0.3"), "AWAY": Decimal("0.3")},
        {"status": "READY"},
        None,
        {"status": "READY"},
        {"count": 2},
        "MARKET_REFERENCE_ONLY",
        "PARTIAL",
        "UNAVAILABLE",
        "UNAVAILABLE",
        None,
        "PARTIAL",
    )
    assert persist_shadow_analysis(db, write)
    assert not persist_shadow_analysis(db, write)
    assert (
        db.execute(
            text("SELECT count(*) FROM shadow_analysis_snapshots WHERE publication_eligible=true")
        ).scalar_one()
        == 0
    )
    assert db.execute(text("SELECT count(*) FROM prediction_snapshots")).scalar_one() == 0


@pytest.mark.integration
def test_shadow_database_rejects_publication_promotion(db: Connection) -> None:
    _teams(db)
    payload = _payload()
    run_id = deterministic_run_id((payload,), NOW)
    sync = persist_current_season_payloads(
        db,
        (payload,),
        logical_run_id=run_id,
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    actual_run_id = db.execute(
        text(
            "SELECT run_id FROM engine_runs WHERE logical_run_id = :id ORDER BY attempt_number DESC LIMIT 1"
        ),
        {"id": run_id},
    ).scalar_one()
    write = ShadowAnalysisWrite(
        actual_run_id,
        run_id,
        sync.match_ids[0][1],
        NOW,
        "raw_ml_v1",
        "features_v1",
        {"HOME": Decimal("1")},
        None,
        None,
        None,
        None,
        "MODEL_ONLY",
        "PARTIAL",
        "UNAVAILABLE",
        "UNAVAILABLE",
        None,
        "PARTIAL",
    )
    persist_shadow_analysis(db, write)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text("UPDATE shadow_analysis_snapshots SET publication_eligible=true WHERE run_id=:id"),
            {"id": actual_run_id},
        )


def test_semantic_run_identity_ignores_payload_order() -> None:
    first = _payload(fixture_id=1)
    second = _payload(fixture_id=2)
    assert deterministic_run_id((first, second), NOW) == deterministic_run_id((second, first), NOW)


@pytest.mark.integration
def test_duplicate_provider_row_does_not_duplicate_fixture(db: Connection) -> None:
    _teams(db)
    payload = _payload()
    result = persist_current_season_payloads(
        db,
        (payload, payload),
        logical_run_id=deterministic_run_id((payload, payload), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert [item.status.value for item in result.fixture_writes] == ["INSERTED", "UNCHANGED"]
    assert len(set(result.match_ids)) == 1


@pytest.mark.integration
def test_provider_id_replacement_requires_review(db: Connection) -> None:
    _teams(db)
    payload = _payload()
    first = persist_current_season_payloads(
        db,
        (payload,),
        logical_run_id=deterministic_run_id((payload,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    replacement = _payload(fixture_id=900099)
    reviewed = persist_current_season_payloads(
        db,
        (replacement,),
        logical_run_id=deterministic_run_id((replacement,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=2),
        prediction_as_of=NOW,
    )
    assert first.fixture_writes[0].status.value == "INSERTED"
    assert reviewed.fixture_writes[0].status.value == "PROVIDER_ID_REPLACEMENT_REVIEW"
    assert reviewed.fixture_writes[0].match_id is None


def test_shadow_contract_rejects_publication() -> None:
    with pytest.raises(ValueError, match="never"):
        ShadowAnalysisWrite(
            "run",
            "logical_run",
            1,
            NOW,
            "model",
            "features",
            {"HOME": Decimal("1")},
            None,
            None,
            None,
            None,
            "MODEL_ONLY",
            "PARTIAL",
            "UNAVAILABLE",
            "UNAVAILABLE",
            None,
            "PARTIAL",
            publication_eligible=True,
        )


@pytest.mark.integration
def test_systemic_persistence_failure_rolls_back_run_unit(
    db: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _teams(db)
    payload = _payload(fixture_id=900777, home_id=910777, away_id=910778)

    def fail(*args: object, **kwargs: object) -> object:
        raise RuntimeError("simulated database boundary failure")

    monkeypatch.setattr(current_season, "persist_fixture", fail)
    with pytest.raises(RuntimeError), db.begin_nested():
        persist_current_season_payloads(
            db,
            (payload,),
            logical_run_id=deterministic_run_id((payload,), NOW),
            window_start=NOW,
            window_end=NOW + timedelta(days=2),
            prediction_as_of=NOW,
        )
    count = db.execute(
        text(
            """SELECT count(*) FROM source_entity_references
            WHERE provider_entity_id IN ('900777','910777','910778')"""
        )
    ).scalar_one()
    assert count == 0
