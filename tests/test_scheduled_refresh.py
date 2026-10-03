from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Connection

import pitchvalue.operations.scheduled_refresh as scheduled_refresh
from pitchvalue.operations.contracts import RunStatus
from pitchvalue.operations.events import EventType, OperationalEvent
from pitchvalue.providers.five_dfa.client import RateLimitState
from pitchvalue.providers.five_dfa.config import FiveDfaConfig

TUESDAY = datetime(2026, 10, 6, 8, tzinfo=UTC)
FRIDAY = datetime(2026, 10, 9, 8, tzinfo=UTC)


class FakeAdapter:
    def __init__(self) -> None:
        self.windows: list[tuple[datetime, datetime]] = []
        self.odds_calls = 0

    def fixture_payloads(
        self, *, start_time: datetime, end_time: datetime, league_id: str | None = None
    ) -> tuple[tuple[Mapping[str, object], ...], tuple[RateLimitState, ...]]:
        del league_id
        self.windows.append((start_time, end_time))
        payload = {"id": len(self.windows), "kickoff_utc": start_time.isoformat()}
        return (payload,), (RateLimitState(100, 99, None, None),)

    def fixture_odds_payload(self, provider_fixture_id: str) -> Mapping[str, object]:
        del provider_fixture_id
        self.odds_calls += 1
        raise AssertionError("scheduled refresh must not fetch odds")


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
