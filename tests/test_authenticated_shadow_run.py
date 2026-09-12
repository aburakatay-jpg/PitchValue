from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pitchvalue.operations import manual_shadow_run as shadow
from pitchvalue.providers.five_dfa.config import load_five_dfa_project_config
from pitchvalue.providers.five_dfa.fixtures import parse_runtime_fixture
from pitchvalue.providers.five_dfa.mapping import MappingStatus, map_competition

NOW = datetime(2026, 9, 13, 2, tzinfo=UTC)


def _payload() -> dict[str, object]:
    return {
        "id": 101,
        "kickoff_utc": "2026-09-13T13:30:00+00:00",
        "status": "scheduled",
        "status_code": "NS",
        "status_reason": None,
        "goals": {"home": 0, "away": 0},
        "league": {"id": 686337048, "name": "Germany Bundesliga I"},
        "teams": {
            "home": {"id": 10, "name": "RB Leipzig"},
            "away": {"id": 20, "name": "Hamburg"},
        },
        "corners": {"home": 0, "away": 0},
        "cards": {
            "home": {"yellow": 0, "red": 0},
            "away": {"yellow": 0, "red": 0},
        },
    }


def test_project_config_reads_ignored_dotenv_without_exposing_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FIVEDFA_API_KEY=private-value\nFIVEDFA_PLAN=FREE\n", encoding="utf-8")
    config = load_five_dfa_project_config({}, env_path=env_file)
    assert config.api_key == "private-value"
    assert "private-value" not in repr(config)


def test_process_environment_precedes_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FIVEDFA_API_KEY=file-value\n", encoding="utf-8")
    config = load_five_dfa_project_config({"FIVEDFA_API_KEY": "process-value"}, env_path=env_file)
    assert config.api_key == "process-value"


@pytest.mark.parametrize(
    ("runtime_name", "canonical"),
    [
        ("England Premier League", "Premier League"),
        ("France Ligue 1", "Ligue 1"),
        ("Germany Bundesliga I", "Bundesliga"),
        ("Spain La Liga", "La Liga"),
    ],
)
def test_authenticated_runtime_competition_aliases_are_explicit(
    runtime_name: str, canonical: str
) -> None:
    result = map_competition("opaque", runtime_name)
    assert result.status is MappingStatus.RESOLVED
    assert result.canonical_name == canonical


def test_serie_a_runtime_access_does_not_expand_pitchvalue_scope() -> None:
    result = map_competition("opaque", "Italy Serie A")
    assert result.status is MappingStatus.UNSUPPORTED
    assert result.canonical_name is None


def test_runtime_fixture_parser_uses_nested_teams_and_explicit_ids() -> None:
    fixture = parse_runtime_fixture(_payload(), explicit_team_mappings={"10": 1, "20": 2})
    assert fixture.competition.canonical_name == "Bundesliga"
    assert fixture.home_team.canonical_team_id == 1
    assert fixture.away_team.canonical_team_id == 2
    assert fixture.statistics.home_corners == 0
    assert fixture.statistics.away_red_cards == 0


def test_shadow_run_requires_database_enforced_read_only() -> None:
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = "off"
    with pytest.raises(RuntimeError, match="read-only transaction"):
        shadow.run_authenticated_shadow(
            connection,
            MagicMock(),
            start_time=NOW,
            end_time=NOW + timedelta(hours=12),
            prediction_as_of=NOW,
        )


def test_unresolved_real_fixture_is_deterministic_nonpublic_and_network_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = "on"
    adapter = MagicMock()
    limit = SimpleNamespace(limit=60, remaining=59)
    adapter.fixture_payloads.return_value = ((_payload(),), (limit,))
    monkeypatch.setattr(shadow, "_database_counts", lambda connection: (("matches", 1),))
    monkeypatch.setattr(shadow, "_explicit_team_mappings", lambda connection, rows: {})
    monkeypatch.setattr(shadow, "_competition_contexts", lambda connection: {})
    monkeypatch.setattr(
        shadow,
        "load_real_match_result_dataset",
        lambda connection: SimpleNamespace(dataset=SimpleNamespace(rows=())),
    )
    monkeypatch.setattr(shadow, "fit_multinomial_logistic", lambda rows: object())
    first = shadow.run_authenticated_shadow(
        connection,
        adapter,
        start_time=NOW,
        end_time=NOW + timedelta(hours=12),
        prediction_as_of=NOW,
    )
    second = shadow.run_authenticated_shadow(
        connection,
        adapter,
        start_time=NOW,
        end_time=NOW + timedelta(hours=12),
        prediction_as_of=NOW,
    )
    assert first.to_dict() == second.to_dict()
    assert first.quarantined == 1 and first.eligible == 0
    assert first.database_writes == 0
    assert first.public_eligible_predictions == 0
    assert first.fixture_requests == 1 and first.odds_requests == 0


def test_local_reports_are_secret_free_and_publication_disabled(tmp_path: Path) -> None:
    fixture = shadow.ShadowFixtureResult(
        "101",
        "Bundesliga",
        NOW + timedelta(hours=2),
        "Home",
        "Away",
        1,
        2,
        shadow.GateStatus.ELIGIBLE,
        (),
        (("HOME", shadow.Decimal("0.5")),),
    )
    report = shadow.AuthenticatedShadowRunReport(
        shadow.SHADOW_RUN_VERSION,
        "shadow-test",
        "5DollarFootballAPI",
        "FREE",
        NOW,
        NOW + timedelta(hours=12),
        NOW,
        "AUTHENTICATED_READ_ONLY_DRY_RUN",
        1,
        0,
        0,
        60,
        59,
        1,
        1,
        0,
        (),
        (("ML", 1),),
        (("MODEL_ONLY", 1),),
        (("ADD", 1),),
        "PENDING",
        "UNAVAILABLE",
        "FINAL_CHECK_UNAVAILABLE",
        "UNAVAILABLE",
        0,
        1,
        (("prediction_snapshots", 0),),
        (("prediction_snapshots", 0),),
        0,
        0,
        "DRY_RUN_LIVE_SYNC_WRITE_PATH_UNAVAILABLE",
        ("RUN_STARTED", "RUN_SUCCEEDED"),
        (fixture,),
        (),
    )
    directory = shadow.write_local_reports(report, tmp_path)
    summary = (directory / "run-summary.json").read_text(encoding="utf-8")
    assert "FIVEDFA_API_KEY" not in summary
    assert "Authorization" not in summary
    assert json.loads(summary)["public_eligible_predictions"] == 0
    assert {path.name for path in directory.iterdir()} == {
        "run-summary.json",
        "fixtures.csv",
        "predictions.csv",
        "market-evaluations.csv",
        "data-quality.csv",
        "quarantined-matches.csv",
        "errors.json",
    }
    changed_quota = replace(report, rate_limit_remaining=12, request_ids_supplied=1)
    assert changed_quota.to_dict()["fingerprint"] == report.to_dict()["fingerprint"]
