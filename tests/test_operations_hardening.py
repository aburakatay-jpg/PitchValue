from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations import persisted_shadow_run
from pitchvalue.operations.events import EventType, ReasonCode
from pitchvalue.operations.hardening import (
    FailureClass,
    HealthState,
    ProviderQuotaError,
    RunLockError,
    RunLockResult,
    canonical_json,
    classify_failure,
    ensure_provider_quota,
    evaluate_health,
    evaluate_readiness,
    failure_event_contract,
    load_activation_gates,
    recover_stale_run,
    run_lock,
    stale_runs,
    validate_manual_window,
    validate_report_root,
)
from pitchvalue.operations.status import system_status
from pitchvalue.providers.five_dfa.client import (
    FiveDfaError,
    ProviderErrorKind,
    RateLimitState,
)

NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)
TEST_RUN = "operations-hardening-stale-test"
EVENT_FAILURE_RUN = "operations-hardening-event-failure-test"


@pytest.fixture(scope="session")
def hardening_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


def test_activation_gates_are_explicit_and_fail_closed() -> None:
    assert load_activation_gates({}).safe_for_shadow
    assert not load_activation_gates({"SCHEDULER_ENABLED": "true"}).safe_for_shadow
    with pytest.raises(ValueError, match="explicitly"):
        load_activation_gates({"PUBLICATION_ENABLED": "yes"})


def test_manual_window_is_timezone_aware_and_bounded() -> None:
    validate_manual_window(NOW, NOW + timedelta(days=1), 8)
    with pytest.raises(ValueError, match="positive"):
        validate_manual_window(NOW, NOW, 8)
    with pytest.raises(ValueError, match="bounded"):
        validate_manual_window(NOW, NOW + timedelta(days=8), 8)
    with pytest.raises(ValueError, match="between"):
        validate_manual_window(NOW, NOW + timedelta(days=1), 21)


def test_report_root_requires_an_available_directory(tmp_path: Path) -> None:
    validate_report_root(tmp_path)
    validate_report_root(tmp_path / "new-report")
    with pytest.raises(ValueError, match="unavailable"):
        validate_report_root(tmp_path / "missing-parent" / "report")


def test_quota_preflight_uses_known_remaining_and_conservative_unknown_budget() -> None:
    ensure_provider_quota((RateLimitState(60, 8, None, None),), expected_additional_calls=8)
    with pytest.raises(ProviderQuotaError, match="INSUFFICIENT"):
        ensure_provider_quota((RateLimitState(60, 7, None, None),), expected_additional_calls=8)
    ensure_provider_quota((), expected_additional_calls=8)
    with pytest.raises(ProviderQuotaError, match="UNKNOWN"):
        ensure_provider_quota((), expected_additional_calls=9)


def test_failure_classification_preserves_systemic_and_local_boundaries() -> None:
    transient = FiveDfaError(ProviderErrorKind.TIMEOUT, "provider_timeout")
    permanent = FiveDfaError(ProviderErrorKind.AUTHENTICATION, "invalid_api_key")
    assert classify_failure(transient) is FailureClass.PROVIDER_TRANSIENT
    assert classify_failure(permanent) is FailureClass.PROVIDER_PERMANENT
    assert classify_failure(ValueError(), stage="fixture") is FailureClass.FIXTURE_LOCAL
    assert classify_failure(ValueError(), stage="market_family") is FailureClass.MARKET_FAMILY_LOCAL
    assert classify_failure(RuntimeError(), stage="persistence") is FailureClass.PERSISTENCE


def test_failure_classes_map_to_existing_durable_event_taxonomy() -> None:
    assert failure_event_contract(FailureClass.PROVIDER_TRANSIENT) == (
        EventType.PROVIDER_FAILED,
        ReasonCode.PROVIDER_UNAVAILABLE,
    )
    assert failure_event_contract(FailureClass.REPORTING) == (
        EventType.REPORT_ARCHIVE_FAILED,
        ReasonCode.REPORT_ARCHIVE_FAILED,
    )


@pytest.mark.integration
def test_postgres_run_lock_rejects_collision_allows_independent_and_releases(
    hardening_engine: Engine,
) -> None:
    with hardening_engine.connect() as first, hardening_engine.connect() as second:
        with run_lock(first, "same-run") as result:
            assert result is RunLockResult.RUN_LOCK_ACQUIRED
            with (
                pytest.raises(RunLockError, match="RUN_ALREADY_ACTIVE"),
                run_lock(second, "same-run"),
            ):
                pass
            with run_lock(second, "independent-run"):
                pass
        with run_lock(second, "same-run"):
            pass
        with pytest.raises(RuntimeError, match="boom"), run_lock(first, "exception-run"):
            raise RuntimeError("boom")
        with run_lock(second, "exception-run"):
            pass


def _delete_test_run(engine: Engine, run_id: str = TEST_RUN) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM operational_events WHERE run_id=:run"), {"run": run_id}
        )
        connection.execute(text("DELETE FROM engine_runs WHERE run_id=:run"), {"run": run_id})


def _insert_running_test_run(engine: Engine, run_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO engine_runs(
                run_id,logical_run_id,attempt_number,run_type,scheduled_for,started_at,status,schedule_version,
                fixture_horizon,model_version,feature_profile,orchestrator_version,
                policy_version,dq_version,market_stability_version,
                calibration_confidence_version,no_vig_version,provider_contract_version)
                SELECT :run,:run,1,'SHADOW',:scheduled,:started,'RUNNING',schedule_version,
                fixture_horizon,model_version,feature_profile,orchestrator_version,
                policy_version,dq_version,market_stability_version,
                calibration_confidence_version,no_vig_version,provider_contract_version
                FROM engine_runs ORDER BY persisted_at LIMIT 1"""
            ),
            {
                "run": run_id,
                "scheduled": NOW - timedelta(hours=4),
                "started": NOW - timedelta(hours=3),
            },
        )


@pytest.mark.integration
def test_stale_run_recovery_is_explicit_audited_and_idempotent(
    hardening_engine: Engine,
) -> None:
    _delete_test_run(hardening_engine)
    try:
        _insert_running_test_run(hardening_engine, TEST_RUN)
        with hardening_engine.begin() as connection:
            candidates = stale_runs(connection, now=NOW, older_than=timedelta(hours=2))
            assert any(item.run_id == TEST_RUN and not item.lock_active for item in candidates)
            result = recover_stale_run(connection, TEST_RUN, now=NOW, older_than=timedelta(hours=2))
            assert result.code == "RUN_LOCK_STALE_RECOVERED"
        with hardening_engine.begin() as connection:
            again = recover_stale_run(connection, TEST_RUN, now=NOW, older_than=timedelta(hours=2))
            assert again.code == "RUN_NOT_STALE"
            assert (
                connection.execute(
                    text("SELECT status FROM engine_runs WHERE run_id=:run"), {"run": TEST_RUN}
                ).scalar_one()
                == "FAILED"
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM operational_events WHERE run_id=:run"),
                    {"run": TEST_RUN},
                ).scalar_one()
                == 1
            )
    finally:
        _delete_test_run(hardening_engine)


@pytest.mark.integration
def test_event_persistence_failure_cannot_strand_started_run(
    hardening_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _delete_test_run(hardening_engine, EVENT_FAILURE_RUN)
    _insert_running_test_run(hardening_engine, EVENT_FAILURE_RUN)

    def fail_event_write(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("injected event persistence failure")

    monkeypatch.setattr(persisted_shadow_run, "_fail_run", fail_event_write)
    try:
        persisted_shadow_run._mark_started_run_failed(hardening_engine, EVENT_FAILURE_RUN, NOW)
        with hardening_engine.connect() as connection:
            status = connection.execute(
                text("SELECT status FROM engine_runs WHERE run_id=:run"),
                {"run": EVENT_FAILURE_RUN},
            ).scalar_one()
        assert status == "FAILED"
    finally:
        _delete_test_run(hardening_engine, EVENT_FAILURE_RUN)


@pytest.mark.integration
def test_readiness_separates_optional_and_required_provider_config() -> None:
    settings = load_settings(os.environ)
    without_provider = {key: value for key, value in os.environ.items() if key != "FIVEDFA_API_KEY"}
    offline = evaluate_readiness(settings, without_provider, provider_required=False)
    live = evaluate_readiness(settings, without_provider, provider_required=True)
    assert offline.state is HealthState.HEALTHY
    assert offline.ready
    assert live.state is HealthState.UNHEALTHY
    assert not live.ready
    assert "PROVIDER_CONFIGURATION_INVALID" in live.reasons


@pytest.mark.integration
def test_health_is_infrastructure_only_and_separate_from_readiness() -> None:
    health = evaluate_health(load_settings(os.environ))
    assert health.state is HealthState.HEALTHY
    assert health.database_reachable
    assert health.migration_current
    assert health.reasons == ()


@pytest.mark.integration
def test_operator_status_is_secret_safe_and_does_not_probe_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "operator-status-must-never-leak"
    monkeypatch.setenv("FIVEDFA_API_KEY", secret)
    status = system_status()
    health = status["health"]
    readiness = status["readiness"]
    provider = status["provider"]
    assert isinstance(health, dict) and health["state"] == "HEALTHY"
    assert isinstance(readiness, dict) and readiness["state"] == "HEALTHY"
    assert isinstance(provider, dict) and provider["authenticated"] == "NOT_PROBED"
    assert status["public_eligible_predictions"] == 0
    assert secret not in canonical_json(status)


def test_operator_status_reports_unhealthy_database_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pitchvalue.operations.status.evaluate_health",
        lambda settings: SimpleNamespace(
            database_reachable=False,
            to_dict=lambda: {"state": "UNHEALTHY", "reasons": ["DATABASE_UNAVAILABLE"]},
        ),
    )
    monkeypatch.setattr(
        "pitchvalue.operations.status.evaluate_readiness",
        lambda settings, values, provider_required: SimpleNamespace(
            to_dict=lambda: {"state": "UNHEALTHY"}
        ),
    )
    status = system_status()
    health = status["health"]
    assert isinstance(health, dict) and health["state"] == "UNHEALTHY"
    assert status["recent_runs"] == []
    assert status["public_eligible_predictions"] is None
