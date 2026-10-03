from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Connection

import pitchvalue.operations.scheduled_refresh as scheduled_refresh
from pitchvalue.operations.contracts import RunStatus
from pitchvalue.operations.events import EventType, OperationalEvent
from pitchvalue.operations.hardening import RunLockError
from pitchvalue.providers.five_dfa.client import RateLimitState
from pitchvalue.providers.five_dfa.config import FiveDfaConfig

TUESDAY = datetime(2026, 10, 6, 8, tzinfo=UTC)
FRIDAY = datetime(2026, 10, 9, 8, tzinfo=UTC)


class FakeAdapter:
    def __init__(self, lock_state: dict[str, bool] | None = None) -> None:
        self.windows: list[tuple[datetime, datetime]] = []
        self.http_calls = 0
        self.odds_calls = 0
        self.lock_state = lock_state

    def fixture_payloads(
        self, *, start_time: datetime, end_time: datetime, league_id: str | None = None
    ) -> tuple[tuple[Mapping[str, object], ...], tuple[RateLimitState, ...]]:
        del league_id
        if self.lock_state is not None:
            assert self.lock_state["active"]
        self.http_calls += 1
        self.windows.append((start_time, end_time))
        payload = {"id": len(self.windows), "kickoff_utc": start_time.isoformat()}
        return (payload,), (RateLimitState(100, 99, None, None),)

    def fixture_odds_payload(self, provider_fixture_id: str) -> Mapping[str, object]:
        del provider_fixture_id
        self.odds_calls += 1
        raise AssertionError("scheduled refresh must not fetch odds")


def _result(scheduled_for: datetime, attempt: int = 1) -> scheduled_refresh.ScheduledRefreshResult:
    plan = scheduled_refresh.plan_scheduled_refresh(scheduled_for)
    return scheduled_refresh.ScheduledRefreshResult(
        plan.scheduled_for.isoformat(),
        plan.logical_run_id,
        f"{plan.logical_run_id}-attempt-{attempt}",
        attempt,
        tuple(item.isoformat() for item in plan.horizon.local_dates),
        len(plan.horizon.local_dates),
        len(plan.horizon.local_dates),
        len(plan.horizon.local_dates),
        RunStatus.SUCCEEDED.value,
        True,
    )


def _install_run_fakes(
    monkeypatch: pytest.MonkeyPatch,
    prior_rows: list[list[dict[str, object]]],
    persistence_results: list[scheduled_refresh.ScheduledRefreshResult],
) -> tuple[MagicMock, MagicMock, MagicMock, list[str], dict[str, bool]]:
    engine = MagicMock()
    lock_connection = MagicMock(spec=Connection)
    query_results = []
    for rows in prior_rows:
        query_result = MagicMock()
        query_result.mappings.return_value.all.return_value = rows
        query_results.append(query_result)
    lock_connection.execute.side_effect = query_results
    engine.connect.return_value = lock_connection
    persistence_connection = MagicMock(spec=Connection)
    engine.begin.return_value.__enter__.return_value = persistence_connection
    persistence = MagicMock(side_effect=persistence_results)
    locked_identities: list[str] = []
    lock_state = {"active": False}

    @contextmanager
    def fake_run_lock(connection: Connection, semantic_identity: str) -> Iterator[None]:
        assert connection is lock_connection
        locked_identities.append(semantic_identity)
        lock_state["active"] = True
        try:
            yield
        finally:
            lock_state["active"] = False

    monkeypatch.setattr(scheduled_refresh, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(scheduled_refresh, "run_lock", fake_run_lock)
    monkeypatch.setattr(scheduled_refresh, "persist_scheduled_payloads", persistence)
    return engine, lock_connection, persistence, locked_identities, lock_state


@pytest.mark.parametrize(("scheduled_for", "expected"), ((TUESDAY, 3), (FRIDAY, 4)))
def test_frozen_horizon_fetches_one_sequence_per_date(
    scheduled_for: datetime, expected: int
) -> None:
    adapter = FakeAdapter()
    batch = scheduled_refresh.collect_scheduled_payloads(adapter, scheduled_for)

    assert len(batch.horizon.local_dates) == expected
    assert len(adapter.windows) == expected
    assert len(batch.payloads) == expected
    assert all(end - start == timedelta(days=1) for start, end in adapter.windows)
    assert adapter.odds_calls == 0


@pytest.mark.parametrize(
    "scheduled_for",
    (
        datetime(2026, 10, 7, 8, tzinfo=UTC),
        datetime(2026, 10, 6, 9, tzinfo=UTC),
        datetime(2026, 10, 6, 8),
    ),
)
def test_invalid_schedule_timestamp_is_rejected(scheduled_for: datetime) -> None:
    adapter = FakeAdapter()
    with pytest.raises(ValueError, match="timezone-aware|configured run time"):
        scheduled_refresh.collect_scheduled_payloads(adapter, scheduled_for)
    assert adapter.windows == []


def test_collection_never_scans_stale_dates_or_invokes_engine() -> None:
    adapter = FakeAdapter()
    batch = scheduled_refresh.collect_scheduled_payloads(adapter, TUESDAY)

    assert len(batch.payloads) == 3
    assert "refresh_stale" not in scheduled_refresh.__dict__
    assert "orchestrate_match" not in scheduled_refresh.__dict__
    assert "run_persisted_shadow" not in scheduled_refresh.__dict__
    assert adapter.odds_calls == 0


def test_successful_second_invocation_is_provider_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_result = _result(TUESDAY)
    prior_success = {
        "run_id": first_result.run_id,
        "attempt_number": 1,
        "status": RunStatus.SUCCEEDED.value,
    }
    engine, lock_connection, persistence, locked, lock_state = _install_run_fakes(
        monkeypatch,
        [[], [prior_success]],
        [first_result],
    )
    adapter = FakeAdapter(lock_state)

    def clock() -> datetime:
        return TUESDAY + timedelta(minutes=1)

    first = scheduled_refresh.run_scheduled_refresh(
        "postgresql://test", adapter, TUESDAY, clock=clock
    )
    second = scheduled_refresh.run_scheduled_refresh(
        "postgresql://test", adapter, TUESDAY, clock=clock
    )

    assert first.result == RunStatus.SUCCEEDED.value
    assert first.provider_request_performed
    assert second.result == "ALREADY_COMPLETED"
    assert not second.provider_request_performed
    assert second.prior_run_id == first.run_id
    assert second.prior_attempt == 1
    assert second.to_dict()["provider_request_performed"] is False
    assert second.to_dict()["result"] == "ALREADY_COMPLETED"
    assert adapter.http_calls == 3
    assert adapter.odds_calls == 0
    persistence.assert_called_once()
    assert locked == [first.logical_run_id, first.logical_run_id]
    assert lock_connection.rollback.call_count == 2
    assert engine.dispose.call_count == 2


def test_partial_with_quarantines_is_accepted_terminal_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = {
        "run_id": "partial-attempt-1",
        "attempt_number": 1,
        "status": RunStatus.PARTIAL_WITH_QUARANTINES.value,
    }
    _, _, persistence, _, lock_state = _install_run_fakes(monkeypatch, [[prior]], [])
    adapter = FakeAdapter(lock_state)

    result = scheduled_refresh.run_scheduled_refresh(
        "postgresql://test",
        adapter,
        TUESDAY,
        clock=lambda: TUESDAY + timedelta(minutes=1),
    )

    assert result.result == "ALREADY_COMPLETED"
    assert result.prior_run_id == "partial-attempt-1"
    assert adapter.http_calls == 0
    persistence.assert_not_called()


def test_advisory_lock_conflict_blocks_provider_before_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock()
    lock_connection = MagicMock(spec=Connection)
    engine.connect.return_value = lock_connection

    @contextmanager
    def rejected_lock(connection: Connection, semantic_identity: str) -> Iterator[None]:
        del connection, semantic_identity
        raise RunLockError("RUN_ALREADY_ACTIVE")
        yield

    monkeypatch.setattr(scheduled_refresh, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(scheduled_refresh, "run_lock", rejected_lock)
    adapter = FakeAdapter()

    with pytest.raises(RunLockError, match="RUN_ALREADY_ACTIVE"):
        scheduled_refresh.run_scheduled_refresh(
            "postgresql://test",
            adapter,
            TUESDAY,
            clock=lambda: TUESDAY + timedelta(minutes=1),
        )

    assert adapter.http_calls == 0
    assert adapter.odds_calls == 0
    engine.begin.assert_not_called()


def test_failed_prior_attempt_allows_controlled_next_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = {
        "run_id": "failed-attempt-1",
        "attempt_number": 1,
        "status": RunStatus.FAILED.value,
    }
    retry_result = _result(TUESDAY, attempt=2)
    _, _, persistence, _, lock_state = _install_run_fakes(monkeypatch, [[prior]], [retry_result])
    adapter = FakeAdapter(lock_state)

    result = scheduled_refresh.run_scheduled_refresh(
        "postgresql://test",
        adapter,
        TUESDAY,
        clock=lambda: TUESDAY + timedelta(minutes=1),
    )

    assert result.attempt == 2
    assert result.provider_request_performed
    assert adapter.http_calls == 3
    assert adapter.odds_calls == 0
    persistence.assert_called_once()


@pytest.mark.parametrize("status", (RunStatus.SCHEDULED, RunStatus.RUNNING))
def test_active_prior_attempt_refuses_duplicate_before_provider(
    monkeypatch: pytest.MonkeyPatch, status: RunStatus
) -> None:
    prior = {"run_id": "active-attempt-1", "attempt_number": 1, "status": status.value}
    _, _, persistence, _, lock_state = _install_run_fakes(monkeypatch, [[prior]], [])
    adapter = FakeAdapter(lock_state)

    with pytest.raises(RuntimeError, match="SCHEDULED_REFRESH_ALREADY_ACTIVE"):
        scheduled_refresh.run_scheduled_refresh(
            "postgresql://test",
            adapter,
            TUESDAY,
            clock=lambda: TUESDAY + timedelta(minutes=1),
        )

    assert adapter.http_calls == 0
    assert adapter.odds_calls == 0
    persistence.assert_not_called()


def test_different_schedule_identity_runs_independent_provider_sequences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tuesday_result = _result(TUESDAY)
    friday_result = _result(FRIDAY)
    _, _, persistence, locked, lock_state = _install_run_fakes(
        monkeypatch,
        [[], []],
        [tuesday_result, friday_result],
    )
    adapter = FakeAdapter(lock_state)

    scheduled_refresh.run_scheduled_refresh(
        "postgresql://test",
        adapter,
        TUESDAY,
        clock=lambda: TUESDAY + timedelta(minutes=1),
    )
    scheduled_refresh.run_scheduled_refresh(
        "postgresql://test",
        adapter,
        FRIDAY,
        clock=lambda: FRIDAY + timedelta(minutes=1),
    )

    assert locked == [tuesday_result.logical_run_id, friday_result.logical_run_id]
    assert tuesday_result.logical_run_id != friday_result.logical_run_id
    assert adapter.http_calls == 7
    assert adapter.odds_calls == 0
    assert persistence.call_count == 2


def test_persistence_is_called_once_and_writes_scheduled_operational_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeAdapter()
    batch = scheduled_refresh.collect_scheduled_payloads(adapter, FRIDAY)
    connection = MagicMock(spec=Connection)
    update_result = MagicMock()
    update_result.rowcount = 1
    attempt_result = MagicMock()
    attempt_result.scalar_one.return_value = 2
    connection.execute.side_effect = [update_result, attempt_result]
    sync = SimpleNamespace(
        run_id="scheduled-run-attempt-2",
        match_ids=(("1", 101), ("2", 102)),
        terminal_status=RunStatus.SUCCEEDED,
    )
    persist = MagicMock(return_value=sync)
    events: list[OperationalEvent] = []

    def record_event(ignored_connection: Connection, event: OperationalEvent) -> bool:
        del ignored_connection
        events.append(event)
        return True

    monkeypatch.setattr(scheduled_refresh, "persist_current_season_payloads", persist)
    monkeypatch.setattr(scheduled_refresh, "persist_event", record_event)
    result = scheduled_refresh.persist_scheduled_payloads(
        connection,
        batch,
        started_at=FRIDAY + timedelta(minutes=1),
        finished_at=FRIDAY + timedelta(minutes=2),
    )

    persist.assert_called_once()
    assert persist.call_args.args[1] == batch.payloads
    assert len(adapter.windows) == 4
    assert result.date_slice_count == 4
    assert result.attempt == 2
    assert result.canonical_fixture_count == 2
    assert [event.event_type for event in events] == [
        EventType.FIXTURE_REFRESH_STARTED,
        EventType.RUN_SUCCEEDED,
    ]
    assert all(event.metadata["source"] == "scheduled" for event in events)
    assert all(event.metadata["scheduled_for"] == FRIDAY.isoformat() for event in events)
    assert all(event.metadata["attempt"] == "2" for event in events)
    sql = " ".join(str(call.args[0]) for call in connection.execute.call_args_list).upper()
    assert "FROM MATCHES" not in sql
    assert "STALE" not in sql


def test_persistence_replay_reuses_the_collected_batch_without_provider_refetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeAdapter()
    batch = scheduled_refresh.collect_scheduled_payloads(adapter, TUESDAY)
    connection = MagicMock(spec=Connection)
    update_result = MagicMock(rowcount=1)
    attempt_result = MagicMock()
    attempt_result.scalar_one.side_effect = [1, 2]
    connection.execute.side_effect = [
        update_result,
        attempt_result,
        update_result,
        attempt_result,
    ]
    sync = SimpleNamespace(
        run_id="scheduled-run",
        match_ids=(),
        terminal_status=RunStatus.SUCCEEDED,
    )
    persist = MagicMock(return_value=sync)
    monkeypatch.setattr(scheduled_refresh, "persist_current_season_payloads", persist)
    monkeypatch.setattr(scheduled_refresh, "persist_event", lambda connection, event: True)

    for attempt in (1, 2):
        sync.run_id = f"scheduled-run-attempt-{attempt}"
        scheduled_refresh.persist_scheduled_payloads(
            connection,
            batch,
            started_at=TUESDAY + timedelta(minutes=attempt),
            finished_at=TUESDAY + timedelta(minutes=attempt + 1),
        )

    assert persist.call_count == 2
    assert len(adapter.windows) == 3


def test_provider_retry_policy_remains_owned_by_client_configuration() -> None:
    assert FiveDfaConfig("test-key").max_safe_retries == 1
    assert "FIVEDFA_MAX_SAFE_RETRIES" not in scheduled_refresh.__dict__
