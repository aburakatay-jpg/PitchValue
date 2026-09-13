from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

import pitchvalue.operations.current_season as current_season
import pitchvalue.operations.persisted_shadow_run as persisted_shadow
from pitchvalue.config import load_settings
from pitchvalue.operations.current_season import (
    deterministic_run_id,
    persist_current_season_payloads,
)
from pitchvalue.providers.five_dfa.team_mapping_review import (
    REVIEWED_TEAM_MAPPINGS,
    TEAM_MAPPING_REVIEW_VERSION,
    TeamMappingClassification,
    apply_reviewed_team_mappings,
)

NOW = datetime(2026, 9, 13, tzinfo=UTC)


@pytest.fixture(scope="session")
def mapping_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(mapping_engine: Engine) -> Iterator[Connection]:
    with mapping_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _provider_id(db: Connection) -> int:
    return int(
        db.execute(
            text("SELECT provider_id FROM providers WHERE name='5DollarFootballAPI'")
        ).scalar_one()
    )


def test_review_manifest_covers_every_explicitly_observed_identity() -> None:
    assert len(REVIEWED_TEAM_MAPPINGS) == 46
    assert len({item.provider_team_id for item in REVIEWED_TEAM_MAPPINGS}) == 46
    counts = Counter(item.classification for item in REVIEWED_TEAM_MAPPINGS)
    assert counts == {
        TeamMappingClassification.RESOLVED_EXISTING_TEAM: 18,
        TeamMappingClassification.CANONICAL_TEAM_MISSING: 9,
        TeamMappingClassification.OUT_OF_SCOPE: 19,
    }
    assert TEAM_MAPPING_REVIEW_VERSION == "five_dfa_team_review_2026_27_v3"


@pytest.mark.integration
def test_review_resolves_supported_scope_and_marks_serie_a_unsupported(db: Connection) -> None:
    summary = apply_reviewed_team_mappings(db, _provider_id(db))
    assert summary.reviewed == 46
    assert summary.resolved == 27
    assert summary.unsupported == 19
    assert summary.review_required == summary.conflicts == 0
    assert 0 <= summary.canonical_teams_created <= 9
    assert (
        db.execute(
            text("""SELECT count(*) FROM teams WHERE canonical_name=ANY(:names)"""),
            {
                "names": [
                    item.canonical_name
                    for item in REVIEWED_TEAM_MAPPINGS
                    if item.classification is TeamMappingClassification.CANONICAL_TEAM_MISSING
                ]
            },
        ).scalar_one()
        == 9
    )
    statuses = dict(
        db.execute(
            text(
                """SELECT provider_entity_id,mapping_status FROM source_entity_references
                WHERE provider_id=:provider AND entity_type='TEAM'
                  AND provider_entity_id=ANY(:ids)"""
            ),
            {
                "provider": _provider_id(db),
                "ids": [item.provider_team_id for item in REVIEWED_TEAM_MAPPINGS],
            },
        ).all()
    )
    assert Counter(statuses.values()) == {"RESOLVED": 27, "UNSUPPORTED": 19}


@pytest.mark.integration
def test_mapping_application_replays_without_duplicate_teams_or_aliases(db: Connection) -> None:
    provider_id = _provider_id(db)
    first = apply_reviewed_team_mappings(db, provider_id)
    team_count = db.execute(text("SELECT count(*) FROM teams")).scalar_one()
    alias_count = db.execute(
        text("SELECT count(*) FROM team_aliases WHERE provider_id=:provider"),
        {"provider": provider_id},
    ).scalar_one()
    second = apply_reviewed_team_mappings(db, provider_id)
    assert 0 <= first.canonical_teams_created <= 9
    assert second.canonical_teams_created == 0
    assert db.execute(text("SELECT count(*) FROM teams")).scalar_one() == team_count
    assert (
        db.execute(
            text("SELECT count(*) FROM team_aliases WHERE provider_id=:provider"),
            {"provider": provider_id},
        ).scalar_one()
        == alias_count
        == 27
    )


@pytest.mark.integration
def test_provider_display_identity_conflict_is_not_silently_resolved(db: Connection) -> None:
    provider_id = _provider_id(db)
    db.execute(
        text(
            """UPDATE source_entity_references SET provider_display_name='Changed Team'
            WHERE provider_id=:provider AND entity_type='TEAM'
              AND provider_entity_id='762247077'"""
        ),
        {"provider": provider_id},
    )
    summary = apply_reviewed_team_mappings(db, provider_id)
    assert summary.conflicts == 1
    assert (
        db.execute(
            text(
                """SELECT mapping_status FROM source_entity_references
                WHERE provider_id=:provider AND entity_type='TEAM'
                  AND provider_entity_id='762247077'"""
            ),
            {"provider": provider_id},
        ).scalar_one()
        == "CONFLICT"
    )


@pytest.mark.integration
def test_reviewed_mapping_allows_a_previously_unresolved_fixture(db: Connection) -> None:
    payload: dict[str, object] = {
        "id": 990000001,
        "kickoff_utc": (NOW + timedelta(days=100)).isoformat(),
        "status": "scheduled",
        "league": {"id": 100, "name": "England Premier League"},
        "teams": {
            "home": {"id": 762247077, "name": "Man Utd"},
            "away": {"id": 3103334772, "name": "Man City"},
        },
    }
    result = persist_current_season_payloads(
        db,
        (payload,),
        run_id=deterministic_run_id((payload,), NOW),
        window_start=NOW,
        window_end=NOW + timedelta(days=101),
        prediction_as_of=NOW,
    )
    assert len(result.match_ids) == 1
    assert result.fixture_writes[0].status.value == "INSERTED"
    assert result.quarantines_created == 0
    assert (
        db.execute(
            text("SELECT status FROM engine_runs WHERE run_id=:run"), {"run": result.run_id}
        ).scalar_one()
        == "RUNNING"
    )
    persisted_shadow._finish_run(db, result, NOW)
    persisted_shadow._finish_run(db, result, NOW)
    assert (
        db.execute(
            text("SELECT status FROM engine_runs WHERE run_id=:run"), {"run": result.run_id}
        ).scalar_one()
        == "SUCCEEDED"
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM operational_events WHERE run_id=:run"),
            {"run": result.run_id},
        ).scalar_one()
        == 4
    )


@pytest.mark.integration
def test_failed_analysis_marks_running_sync_failed_once(db: Connection) -> None:
    payload: dict[str, object] = {
        "id": 990000002,
        "kickoff_utc": (NOW + timedelta(days=101)).isoformat(),
        "status": "scheduled",
        "league": {"id": 100, "name": "England Premier League"},
        "teams": {
            "home": {"id": 762247077, "name": "Man Utd"},
            "away": {"id": 3103334772, "name": "Man City"},
        },
    }
    result = persist_current_season_payloads(
        db,
        (payload,),
        run_id=deterministic_run_id((payload,), NOW + timedelta(seconds=1)),
        window_start=NOW,
        window_end=NOW + timedelta(days=102),
        prediction_as_of=NOW + timedelta(seconds=1),
    )
    persisted_shadow._fail_run(db, result.run_id, NOW + timedelta(seconds=1))
    persisted_shadow._fail_run(db, result.run_id, NOW + timedelta(seconds=1))
    assert (
        db.execute(
            text("SELECT status FROM engine_runs WHERE run_id=:run"), {"run": result.run_id}
        ).scalar_one()
        == "FAILED"
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM operational_events WHERE run_id=:run"),
            {"run": result.run_id},
        ).scalar_one()
        == 4
    )


def test_out_of_scope_decisions_never_supply_a_canonical_target() -> None:
    out_of_scope = tuple(
        item
        for item in REVIEWED_TEAM_MAPPINGS
        if item.classification is TeamMappingClassification.OUT_OF_SCOPE
    )
    assert {item.provider_name for item in out_of_scope} == {
        "AC Milan",
        "Atalanta",
        "Bologna",
        "Cagliari",
        "Como",
        "Frosinone",
        "Fiorentina",
        "Genoa",
        "Inter Milan",
        "Juventus",
        "Lazio",
        "Lecce",
        "Monza",
        "Napoli",
        "Parma",
        "Roma",
        "Sassuolo",
        "Torino",
        "Udinese",
    }
    assert all(item.canonical_name is None and item.scope == "Serie A" for item in out_of_scope)


def test_multi_window_replay_fetches_fixture_payload_only_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Adapter:
        requests = 0

        def fixture_payloads(self, **_: object) -> tuple[tuple[dict[str, object], ...], tuple[str]]:
            self.requests += 1
            return ({"id": 1},), ("rate-state",)

    observed: list[object] = []

    def persist(*args: object, **kwargs: object) -> object:
        del args
        observed.append(kwargs)
        return object()

    adapter = Adapter()
    monkeypatch.setattr(persisted_shadow, "_persist_materialized_shadow", persist)
    result = persisted_shadow.run_persisted_shadow_with_replay(
        "unused",
        adapter,  # type: ignore[arg-type]
        start_time=NOW,
        end_time=NOW + timedelta(days=1),
        prediction_as_of=NOW,
        report_root=tmp_path,
    )
    assert adapter.requests == 1
    assert len(observed) == 2
    assert result.first is not result.replay


def test_multi_window_sample_is_bounded_and_deterministic() -> None:
    payloads = (
        {"id": 3, "kickoff_utc": "2026-09-14T12:00:00+00:00"},
        {"id": 2, "kickoff_utc": "2026-09-13T12:00:00+00:00"},
        {"id": 1, "kickoff_utc": "2026-09-13T12:00:00+00:00"},
    )
    selected = persisted_shadow._bounded_payloads(payloads, 2)
    assert [item["id"] for item in selected] == [1, 2]
    with pytest.raises(ValueError, match="positive"):
        persisted_shadow._bounded_payloads(payloads, 0)


def test_run_identity_changes_with_reviewed_mapping_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = ({"id": 1},)
    first = deterministic_run_id(payload, NOW)
    monkeypatch.setattr(current_season, "MAPPING_CONTRACT_VERSION", "different-reviewed-map")
    assert deterministic_run_id(payload, NOW) != first
