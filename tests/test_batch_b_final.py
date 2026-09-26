# ruff: noqa: E501
from __future__ import annotations

import os
import time
import typing
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.markets.history.contracts import ObservationRole, TimingSemantics
from pitchvalue.operations.contracts import EngineRun, FixtureHorizon, RunStatus, RunType
from pitchvalue.operations.persisted_shadow_run import _persist_odds
from pitchvalue.operations.repository import persist_run
from pitchvalue.operations.shadow_repository import ShadowAnalysisWrite, persist_shadow_analysis
from pitchvalue.prediction.contracts import MarketFamily, Selection
from pitchvalue.providers.five_dfa.odds import LiveOddsObservation

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture(autouse=True)
def clean_db(engine: Engine) -> typing.Generator[None, None, None]:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO competitions (competition_id, canonical_name, country_code, competition_type, gender) VALUES (1, 'Test', 'GBR', 'domestic_league', 'men') ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO seasons (season_id, competition_id, season_name, start_year, end_year, status) VALUES (1, 1, '2020', 2020, 2021, 'active') ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO teams (team_id, canonical_name, normalized_name) VALUES (1, 'T1', 't1'), (2, 'T2', 't2') ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO matches (match_id, competition_id, season_id, home_team_id, away_team_id, kickoff_at_utc, status) VALUES (1, 1, 1, 1, 2, '2026-09-13 12:00:00', 'SCHEDULED') ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO providers (provider_id, name, provider_type, priority) VALUES (1, 'P1', 'odds', 1) ON CONFLICT DO NOTHING"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM shadow_analysis_snapshots"))
        conn.execute(text("DELETE FROM engine_runs"))
        conn.execute(text("DELETE FROM odds_snapshots"))


def _create_engine_run(logical_id: str) -> EngineRun:
    return EngineRun(
        run_id=f"{logical_id}-attempt-1",
        logical_run_id=logical_id,
        attempt_number=1,
        run_type=RunType.SHADOW,
        scheduled_for=NOW,
        started_at=NOW,
        finished_at=NOW,
        status=RunStatus.SUCCEEDED,
        schedule_version="1",
        fixture_horizon=FixtureHorizon("UTC", (NOW.date(),), "1"),
        model_version="1",
        feature_profile="1",
        orchestrator_version="1",
        policy_version="1",
        dq_version="1",
        market_stability_version="1",
        calibration_confidence_version="1",
        no_vig_version="1",
        provider_contract_version="1",
    )


@pytest.mark.integration
def test_odds_persistence_proofs(engine: Engine) -> None:
    match_id = 1
    provider_id = 1
    unique_fix = f"fix-{datetime.now().timestamp()}"

    obs1 = LiveOddsObservation(
        provider_fixture_id=unique_fix,
        bookmaker="B1",
        market=MarketFamily.MATCH_RESULT,
        selection=Selection.HOME,
        observation_role=ObservationRole.UNKNOWN_PREMATCH,
        decimal_odds=Decimal("2.10"),
        line=None,
        normalization_version="1",
        timing_semantics=TimingSemantics.ROLE_ONLY,
        observed_at=None,
        source_timestamp_evidence=(),
    )
    with engine.begin() as conn:
        inserted1 = _persist_odds(conn, provider_id, match_id, obs1)
        assert inserted1 is True

    time.sleep(0.01)
    with engine.begin() as conn:
        inserted2 = _persist_odds(conn, provider_id, match_id, obs1)
        assert inserted2 is False

    obs2 = LiveOddsObservation(
        provider_fixture_id=unique_fix,
        bookmaker="B1",
        market=MarketFamily.MATCH_RESULT,
        selection=Selection.HOME,
        observation_role=ObservationRole.UNKNOWN_PREMATCH,
        decimal_odds=Decimal("2.20"),
        line=None,
        normalization_version="1",
        timing_semantics=TimingSemantics.ROLE_ONLY,
        observed_at=None,
        source_timestamp_evidence=(),
    )
    time.sleep(0.01)
    with engine.begin() as conn:
        inserted3 = _persist_odds(conn, provider_id, match_id, obs2)
        assert inserted3 is True

    time.sleep(0.01)
    with engine.begin() as conn:
        inserted4 = _persist_odds(conn, provider_id, match_id, obs1)
        assert inserted4 is True

    with engine.begin() as conn:
        count = conn.execute(
            text(
                f"SELECT COUNT(*) FROM odds_snapshots WHERE provider_market_id LIKE '{unique_fix}%' AND decimal_odds IN (2.10, 2.20)"
            )
        ).scalar()
        assert count == 3

    obs_other = LiveOddsObservation(
        provider_fixture_id=unique_fix,
        bookmaker="B1",
        market=MarketFamily.MATCH_RESULT,
        selection=Selection.AWAY,
        observation_role=ObservationRole.UNKNOWN_PREMATCH,
        decimal_odds=Decimal("2.10"),
        line=None,
        normalization_version="1",
        timing_semantics=TimingSemantics.ROLE_ONLY,
        observed_at=None,
        source_timestamp_evidence=(),
    )
    time.sleep(0.01)
    with engine.begin() as conn:
        inserted_other = _persist_odds(conn, provider_id, match_id, obs_other)
        assert inserted_other is True

    with engine.begin() as conn:
        row = conn.execute(
            text(
                f"SELECT observed_at FROM odds_snapshots WHERE provider_market_id LIKE '{unique_fix}%' LIMIT 1"
            )
        ).fetchone()
        assert row is not None and row[0] is None


@pytest.mark.integration
def test_snapshot_same_payload_concurrency(engine: Engine) -> None:
    logical_id = f"concurrency-same-{datetime.now().timestamp()}"
    run = _create_engine_run(logical_id)
    with engine.begin() as conn:
        res = persist_run(conn, run)

    payload = ShadowAnalysisWrite(
        run_id=res.run_id,
        logical_run_id=logical_id,
        match_id=1,
        prediction_as_of=NOW,
        model_version="1",
        feature_version="1",
        raw_ml_probabilities={"home": Decimal("0.5")},
        elo=None,
        poisson=None,
        form=None,
        agreement=None,
        odds_mode="MARKET_REFERENCE_ONLY",
        dq_state="CLEAN",
        market_stability="STABLE",
        calibration_confidence="HIGH",
        bet_score=None,
        bet_score_completeness="UNAVAILABLE",
    )

    with ThreadPoolExecutor(max_workers=2) as executor:

        def insert_payload() -> bool:
            with engine.begin() as conn:
                return persist_shadow_analysis(conn, payload)

        results = list(executor.map(lambda _: insert_payload(), range(2)))

    assert results.count(True) == 1
    assert results.count(False) == 1
    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM shadow_analysis_snapshots WHERE logical_run_id=:lrid"),
            {"lrid": logical_id},
        ).scalar()
        assert count == 1


@pytest.mark.integration
def test_snapshot_conflicting_payload_concurrency(engine: Engine) -> None:
    logical_id = f"concurrency-conflict-{datetime.now().timestamp()}"
    run = _create_engine_run(logical_id)
    with engine.begin() as conn:
        res = persist_run(conn, run)

    payload1 = ShadowAnalysisWrite(
        run_id=res.run_id,
        logical_run_id=logical_id,
        match_id=1,
        prediction_as_of=NOW,
        model_version="1",
        feature_version="1",
        raw_ml_probabilities={"home": Decimal("0.5")},
        elo=None,
        poisson=None,
        form=None,
        agreement=None,
        odds_mode="MARKET_REFERENCE_ONLY",
        dq_state="CLEAN",
        market_stability="STABLE",
        calibration_confidence="HIGH",
        bet_score=None,
        bet_score_completeness="UNAVAILABLE",
    )
    payload2 = ShadowAnalysisWrite(
        run_id=res.run_id,
        logical_run_id=logical_id,
        match_id=1,
        prediction_as_of=NOW,
        model_version="1",
        feature_version="1",
        raw_ml_probabilities={"home": Decimal("0.9")},
        elo=None,
        poisson=None,
        form=None,
        agreement=None,
        odds_mode="MARKET_REFERENCE_ONLY",
        dq_state="CLEAN",
        market_stability="STABLE",
        calibration_confidence="HIGH",
        bet_score=None,
        bet_score_completeness="UNAVAILABLE",
    )

    with ThreadPoolExecutor(max_workers=2) as executor:

        def insert_payload(p: ShadowAnalysisWrite) -> typing.Any:
            with engine.begin() as conn:
                try:
                    return persist_shadow_analysis(conn, p)
                except ValueError as e:
                    return str(e)

        results = list(executor.map(insert_payload, [payload1, payload2]))

    assert results.count(True) == 1
    assert any("shadow semantic identity has conflicting payload" in str(r) for r in results)
    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM shadow_analysis_snapshots WHERE logical_run_id=:lrid"),
            {"lrid": logical_id},
        ).scalar()
        assert count == 1


@pytest.mark.integration
def test_partial_retry(engine: Engine) -> None:
    logical_id = f"partial-retry-{datetime.now().timestamp()}"

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO matches (match_id, competition_id, season_id, home_team_id, away_team_id, kickoff_at_utc, status) VALUES (20002, 1, 1, 1, 2, NOW(), 'SCHEDULED') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO matches (match_id, competition_id, season_id, home_team_id, away_team_id, kickoff_at_utc, status) VALUES (20003, 1, 1, 1, 2, NOW(), 'SCHEDULED') ON CONFLICT DO NOTHING"
            )
        )
        res1 = persist_run(conn, _create_engine_run(logical_id))

    payload_a = ShadowAnalysisWrite(
        run_id=res1.run_id,
        logical_run_id=logical_id,
        match_id=1,
        prediction_as_of=NOW,
        model_version="1",
        feature_version="1",
        raw_ml_probabilities={"home": Decimal("0.5")},
        elo=None,
        poisson=None,
        form=None,
        agreement=None,
        odds_mode="MARKET_REFERENCE_ONLY",
        dq_state="CLEAN",
        market_stability="STABLE",
        calibration_confidence="HIGH",
        bet_score=None,
        bet_score_completeness="UNAVAILABLE",
    )
    payload_b = ShadowAnalysisWrite(
        run_id=res1.run_id,
        logical_run_id=logical_id,
        match_id=20002,
        prediction_as_of=NOW,
        model_version="1",
        feature_version="1",
        raw_ml_probabilities={"home": Decimal("0.5")},
        elo=None,
        poisson=None,
        form=None,
        agreement=None,
        odds_mode="MARKET_REFERENCE_ONLY",
        dq_state="CLEAN",
        market_stability="STABLE",
        calibration_confidence="HIGH",
        bet_score=None,
        bet_score_completeness="UNAVAILABLE",
    )
    with engine.begin() as conn:
        assert persist_shadow_analysis(conn, payload_a) is True
        assert persist_shadow_analysis(conn, payload_b) is True

    # Attempt 2
    with engine.begin() as conn:
        res2 = persist_run(conn, _create_engine_run(logical_id))

    payload_c = ShadowAnalysisWrite(
        run_id=res2.run_id,
        logical_run_id=logical_id,
        match_id=20003,
        prediction_as_of=NOW,
        model_version="1",
        feature_version="1",
        raw_ml_probabilities={"home": Decimal("0.5")},
        elo=None,
        poisson=None,
        form=None,
        agreement=None,
        odds_mode="MARKET_REFERENCE_ONLY",
        dq_state="CLEAN",
        market_stability="STABLE",
        calibration_confidence="HIGH",
        bet_score=None,
        bet_score_completeness="UNAVAILABLE",
    )

    with engine.begin() as conn:
        payload_a2 = ShadowAnalysisWrite(**{**payload_a.__dict__, "run_id": res2.run_id})
        payload_b2 = ShadowAnalysisWrite(**{**payload_b.__dict__, "run_id": res2.run_id})

        assert persist_shadow_analysis(conn, payload_a2) is False
        assert persist_shadow_analysis(conn, payload_b2) is False
        assert persist_shadow_analysis(conn, payload_c) is True

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM shadow_analysis_snapshots WHERE logical_run_id=:lrid"),
            {"lrid": logical_id},
        ).scalar()
        assert count == 3

        r1 = conn.execute(
            text(
                "SELECT run_id FROM shadow_analysis_snapshots WHERE logical_run_id=:lrid AND match_id=1"
            ),
            {"lrid": logical_id},
        ).scalar()
        r2 = conn.execute(
            text(
                "SELECT run_id FROM shadow_analysis_snapshots WHERE logical_run_id=:lrid AND match_id=20002"
            ),
            {"lrid": logical_id},
        ).scalar()
        r3 = conn.execute(
            text(
                "SELECT run_id FROM shadow_analysis_snapshots WHERE logical_run_id=:lrid AND match_id=20003"
            ),
            {"lrid": logical_id},
        ).scalar()

        assert r1 == res1.run_id
        assert r2 == res1.run_id
        assert r3 == res2.run_id


@pytest.mark.integration
def test_repeat_after_success_policy(engine: Engine) -> None:
    # Policy B: new physical attempt allowed, semantic snapshots reused
    logical_id = f"repeat-success-{datetime.now().timestamp()}"
    with engine.begin() as conn:
        res1 = persist_run(conn, _create_engine_run(logical_id))

    payload = ShadowAnalysisWrite(
        run_id=res1.run_id,
        logical_run_id=logical_id,
        match_id=1,
        prediction_as_of=NOW,
        model_version="1",
        feature_version="1",
        raw_ml_probabilities={"home": Decimal("0.5")},
        elo=None,
        poisson=None,
        form=None,
        agreement=None,
        odds_mode="MARKET_REFERENCE_ONLY",
        dq_state="CLEAN",
        market_stability="STABLE",
        calibration_confidence="HIGH",
        bet_score=None,
        bet_score_completeness="UNAVAILABLE",
    )
    with engine.begin() as conn:
        assert persist_shadow_analysis(conn, payload) is True

    # New physical attempt ALLOWED
    with engine.begin() as conn:
        res2 = persist_run(conn, _create_engine_run(logical_id))
        assert res2.attempt_number == res1.attempt_number + 1

    payload2 = ShadowAnalysisWrite(**{**payload.__dict__, "run_id": res2.run_id})
    with engine.begin() as conn:
        # semantic snapshot REUSED
        assert persist_shadow_analysis(conn, payload2) is False
