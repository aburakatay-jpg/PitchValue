"""Authenticated current-season persistence followed by internal shadow analysis."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations.contracts import RunStatus
from pitchvalue.operations.current_season import (
    CurrentSeasonPersistenceResult,
    deterministic_run_id,
    persist_current_season_payloads,
)
from pitchvalue.operations.events import (
    DeliveryVisibility,
    EventType,
    OperationalEvent,
    ReasonCode,
    severity_for,
)
from pitchvalue.operations.hardening import (
    ensure_provider_quota,
    evaluate_readiness,
    load_activation_gates,
    run_lock,
    validate_manual_window,
    validate_report_root,
)
from pitchvalue.operations.manual_shadow_run import (
    AuthenticatedShadowRunReport,
    GateStatus,
    run_authenticated_shadow,
    write_local_reports,
)
from pitchvalue.operations.repository import persist_event
from pitchvalue.operations.shadow_repository import ShadowAnalysisWrite, persist_shadow_analysis
from pitchvalue.providers.five_dfa.adapter import FiveDfaFreeAdapter
from pitchvalue.providers.five_dfa.client import FiveDfaClient
from pitchvalue.providers.five_dfa.config import load_five_dfa_project_config
from pitchvalue.providers.five_dfa.odds import LiveOddsObservation, normalize_bet365_snapshot
from pitchvalue.quality.contracts import (
    DataQualityEvaluation,
    EvidenceAvailability,
    EvidenceFamily,
    EvidenceProfile,
    QualityEvidence,
)
from pitchvalue.quality.repository import persist_evaluation


@dataclass(frozen=True)
class PersistedShadowResult:
    report: AuthenticatedShadowRunReport
    sync: CurrentSeasonPersistenceResult
    shadow_created: int
    shadow_reused: int
    odds_created: int
    odds_reused: int
    dq_created: int
    report_directory: Path


@dataclass(frozen=True)
class PersistedShadowReplayResult:
    first: PersistedShadowResult
    replay: PersistedShadowResult


class _ReplayAdapter:
    def __init__(
        self,
        payloads: tuple[dict[str, object], ...],
        rate_states: tuple[Any, ...],
        real: FiveDfaFreeAdapter,
    ) -> None:
        self.payloads = payloads
        self.rate_states = rate_states
        self.real = real
        self.odds_payloads: dict[str, dict[str, object]] = {}

    def fixture_payloads(
        self, **_: object
    ) -> tuple[tuple[dict[str, object], ...], tuple[Any, ...]]:
        return self.payloads, self.rate_states

    def fixture_odds_payload(self, fixture_id: str) -> dict[str, object]:
        if fixture_id not in self.odds_payloads:
            self.odds_payloads[fixture_id] = dict(self.real.fixture_odds_payload(fixture_id))
        return self.odds_payloads[fixture_id]


def run_persisted_shadow(
    database_url: str,
    adapter: FiveDfaFreeAdapter,
    *,
    start_time: datetime,
    end_time: datetime,
    prediction_as_of: datetime,
    report_root: Path,
    max_fixtures: int | None = None,
) -> PersistedShadowResult:
    """Persist authentic source evidence and never-public shadow analysis replay-safely."""
    validate_manual_window(start_time, end_time, max_fixtures)
    payloads, rate_states = adapter.fixture_payloads(start_time=start_time, end_time=end_time)
    materialized = _bounded_payloads(payloads, max_fixtures)
    ensure_provider_quota(rate_states, expected_additional_calls=len(materialized))
    replay = _ReplayAdapter(materialized, rate_states, adapter)
    return _persist_materialized_shadow(
        database_url,
        replay,
        start_time=start_time,
        end_time=end_time,
        prediction_as_of=prediction_as_of,
        report_root=report_root,
    )


def run_persisted_shadow_with_replay(
    database_url: str,
    adapter: FiveDfaFreeAdapter,
    *,
    start_time: datetime,
    end_time: datetime,
    prediction_as_of: datetime,
    report_root: Path,
    max_fixtures: int | None = None,
) -> PersistedShadowReplayResult:
    """Fetch once, then prove deterministic persistence replay without another network call."""
    validate_manual_window(start_time, end_time, max_fixtures)
    payloads, rate_states = adapter.fixture_payloads(start_time=start_time, end_time=end_time)
    materialized = _bounded_payloads(payloads, max_fixtures)
    ensure_provider_quota(rate_states, expected_additional_calls=len(materialized))
    replay = _ReplayAdapter(materialized, rate_states, adapter)
    first = _persist_materialized_shadow(
        database_url,
        replay,
        start_time=start_time,
        end_time=end_time,
        prediction_as_of=prediction_as_of,
        report_root=report_root,
    )
    second = _persist_materialized_shadow(
        database_url,
        replay,
        start_time=start_time,
        end_time=end_time,
        prediction_as_of=prediction_as_of,
        report_root=report_root,
    )
    return PersistedShadowReplayResult(first, second)


def _persist_materialized_shadow(
    database_url: str,
    replay: _ReplayAdapter,
    *,
    start_time: datetime,
    end_time: datetime,
    prediction_as_of: datetime,
    report_root: Path,
) -> PersistedShadowResult:
    materialized = replay.payloads
    logical_run_id = deterministic_run_id(materialized, prediction_as_of)
    engine = create_engine(database_url, pool_pre_ping=True)
    lock_connection: Connection | None = None
    lock_context: Any = None
    lock_acquired = False
    sync: CurrentSeasonPersistenceResult | None = None
    try:
        lock_connection = engine.connect()
        lock_context = run_lock(lock_connection, logical_run_id)
        lock_context.__enter__()
        lock_acquired = True
        with engine.begin() as connection:
            sync = persist_current_season_payloads(
                connection,
                materialized,
                logical_run_id=logical_run_id,
                window_start=start_time,
                window_end=end_time,
                prediction_as_of=prediction_as_of,
            )
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            report = run_authenticated_shadow(
                connection,
                replay,  # type: ignore[arg-type]
                start_time=start_time,
                end_time=end_time,
                prediction_as_of=prediction_as_of,
            )
        match_ids = dict(sync.match_ids)
        shadow_created = shadow_reused = odds_created = odds_reused = dq_created = 0
        with engine.begin() as connection:
            for fixture in report.fixtures:
                match_id = match_ids.get(fixture.provider_fixture_id)
                if fixture.gate_status is not GateStatus.ELIGIBLE or match_id is None:
                    continue
                models = dict(fixture.model_statuses)
                created = persist_shadow_analysis(
                    connection,
                    ShadowAnalysisWrite(
                        sync.run_id,
                        logical_run_id,
                        match_id,
                        prediction_as_of,
                        "raw_multinomial_logistic_v1",
                        "task06_feature_engine_v1",
                        dict(fixture.raw_ml_probabilities),
                        {"status": models.get("ELO", "UNAVAILABLE")},
                        {"status": models.get("POISSON", "UNAVAILABLE")},
                        {"status": models.get("FORM", "UNAVAILABLE")},
                        {"count": fixture.agreement_count},
                        fixture.odds_mode.value,
                        "PARTIAL" if fixture.reasons else "AVAILABLE",
                        report.market_stability,
                        report.calibration_confidence,
                        None,
                        "PARTIAL",
                        ("TIMESTAMP_GATE_PENDING", "BET_SCORE_UNAVAILABLE"),
                    ),
                )
                shadow_created += int(created)
                shadow_reused += int(not created)
                dq_created += int(
                    persist_evaluation(
                        connection,
                        _quality_evaluation(
                            match_id, sync.run_id, prediction_as_of, fixture.history_rows
                        ),
                    )
                )
                odds_payload = replay.odds_payloads.get(fixture.provider_fixture_id)
                if odds_payload is not None:
                    normalized = normalize_bet365_snapshot(odds_payload)
                    for observation in normalized.observations:
                        if _persist_odds(connection, sync.provider_id, match_id, observation):
                            odds_created += 1
                        else:
                            odds_reused += 1
        persisted_writes = (
            shadow_created
            + odds_created
            + dq_created
            + sync.season_inserted
            + sync.quarantines_created
            + sync.events_created
            + sum(item.status.value != "UNCHANGED" for item in sync.fixture_writes)
        )
        report = replace(
            report,
            execution_mode="AUTHENTICATED_PERSISTED_SHADOW",
            database_writes=persisted_writes,
            sync_write_status="PERSISTED_REPLAY_SAFE",
        )
        directory = write_local_reports(report, report_root)
        with engine.begin() as connection:
            _finish_run(connection, sync, prediction_as_of, directory)
        return PersistedShadowResult(
            report,
            sync,
            shadow_created,
            shadow_reused,
            odds_created,
            odds_reused,
            dq_created,
            directory,
        )
    except BaseException:
        if sync is not None:
            _mark_started_run_failed(engine, sync.run_id, prediction_as_of)
        raise
    finally:
        if lock_acquired:
            lock_context.__exit__(None, None, None)
        if lock_connection is not None:
            lock_connection.close()
        engine.dispose()


def _mark_started_run_failed(engine: Engine, run_id: str, occurred_at: datetime) -> None:
    try:
        with engine.begin() as connection:
            _fail_run(connection, run_id, occurred_at)
    except Exception:
        # Event persistence must not strand an already-started run in RUNNING.
        with engine.begin() as connection:
            _set_terminal_status(connection, run_id, RunStatus.FAILED, occurred_at)


def _finish_run(
    connection: Connection,
    sync: CurrentSeasonPersistenceResult,
    occurred_at: datetime,
    report_directory: Path | None = None,
) -> None:
    _set_terminal_status(connection, sync.run_id, sync.terminal_status, occurred_at)
    events = [
        _lifecycle_event(EventType.PERSISTENCE_SUCCEEDED, sync.run_id, occurred_at),
        _lifecycle_event(EventType.RUN_SUCCEEDED, sync.run_id, occurred_at),
    ]
    if report_directory is not None:
        events.insert(
            1,
            _lifecycle_event(
                EventType.REPORT_GENERATION_SUCCEEDED,
                sync.run_id,
                occurred_at,
                metadata={"report_directory": str(report_directory)},
            ),
        )
    for event in events:
        persist_event(connection, event)


def _fail_run(connection: Connection, run_id: str, occurred_at: datetime) -> None:
    if not _set_terminal_status(connection, run_id, RunStatus.FAILED, occurred_at):
        return
    for event_type in (EventType.PERSISTENCE_FAILED, EventType.RUN_FAILED):
        persist_event(connection, _lifecycle_event(event_type, run_id, occurred_at, failed=True))


def _set_terminal_status(
    connection: Connection, run_id: str, status: RunStatus, occurred_at: datetime
) -> bool:
    changed = connection.execute(
        text(
            """UPDATE engine_runs SET status=:status,finished_at=:finished_at
            WHERE run_id=:run_id AND status='RUNNING'"""
        ),
        {"status": status.value, "finished_at": occurred_at, "run_id": run_id},
    ).rowcount
    if changed:
        return True
    existing = connection.execute(
        text("SELECT status FROM engine_runs WHERE run_id=:run_id"), {"run_id": run_id}
    ).scalar_one()
    if existing != status.value and status is not RunStatus.FAILED:
        raise ValueError("engine run has a conflicting terminal status")
    return False


def _lifecycle_event(
    event_type: EventType,
    run_id: str,
    occurred_at: datetime,
    *,
    failed: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> OperationalEvent:
    return OperationalEvent(
        OperationalEvent.deterministic_id(event_type, run_id, "persisted_shadow", event_type.value),
        event_type,
        "persisted_shadow_lifecycle_v1",
        occurred_at,
        severity_for(event_type),
        run_id,
        "persisted_shadow",
        metadata or {"outcome": "failed" if failed else "succeeded"},
        DeliveryVisibility.INTERNAL,
        run_id=run_id,
        provider_domain="fixtures",
        reason_code=ReasonCode.PERSISTENCE_FAILED if failed else None,
    )


def _quality_evaluation(
    match_id: int, run_id: str, at: datetime, history_rows: int
) -> DataQualityEvaluation:
    def evidence(
        family: EvidenceFamily,
        availability: EvidenceAvailability,
        *reasons: str,
        observed_at: datetime | None = None,
    ) -> QualityEvidence:
        return QualityEvidence(
            family,
            availability,
            availability is EvidenceAvailability.HARD_FAIL,
            tuple(sorted(reasons)),
            {"source": "authenticated_shadow", "run_id": run_id},
            observed_at,
        )

    items = (
        evidence(EvidenceFamily.HISTORICAL_DEPTH, EvidenceAvailability.AVAILABLE),
        evidence(
            EvidenceFamily.MATCH_STATISTICS_COMPLETENESS,
            EvidenceAvailability.PARTIAL,
            "OPTIONAL_LIVE_STATS_INCOMPLETE",
        ),
        evidence(
            EvidenceFamily.CURRENT_SEASON_FRESHNESS, EvidenceAvailability.AVAILABLE, observed_at=at
        ),
        evidence(EvidenceFamily.FIXTURE_INTEGRITY, EvidenceAvailability.AVAILABLE),
        evidence(EvidenceFamily.ENTITY_MAPPING_INTEGRITY, EvidenceAvailability.AVAILABLE),
        evidence(
            EvidenceFamily.SOURCE_PROVIDER_HEALTH, EvidenceAvailability.AVAILABLE, observed_at=at
        ),
    )
    version = "live_operational_shadow_dq_v1"
    return DataQualityEvaluation(
        DataQualityEvaluation.deterministic_id(
            match_id, at, EvidenceProfile.LIVE_OPERATIONAL, version
        ),
        match_id,
        run_id,
        at,
        EvidenceProfile.LIVE_OPERATIONAL,
        version,
        items,
    )


def _persist_odds(
    connection: Connection, provider_id: int, match_id: int, item: LiveOddsObservation
) -> bool:
    line = "none" if item.line is None else str(item.line)
    identity = ":".join(
        (
            item.provider_fixture_id,
            item.bookmaker,
            item.market.value,
            item.selection.value,
            item.observation_role.value,
            line,
        )
    )
    # Fetch latest observation for this market
    latest = connection.execute(
        text(
            """SELECT decimal_odds, line FROM odds_snapshots
            WHERE provider_id=:provider_id AND provider_market_id=:identity
              AND normalization_version=:normalization_version
              AND observation_origin='live_source'
            ORDER BY created_at DESC, odds_snapshot_id DESC LIMIT 1"""
        ),
        {
            "provider_id": provider_id,
            "identity": identity,
            "normalization_version": item.normalization_version,
        },
    ).first()

    if latest is not None and latest.decimal_odds == item.decimal_odds and latest.line == item.line:
        return False

    connection.execute(
        text(
            """INSERT INTO odds_snapshots (
                match_id,provider_id,bookmaker,market,selection,line,decimal_odds,
                provider_market_id,observed_at,observation_role,observation_origin,
                observation_source_kind,timing_semantics,quality_status,quality_reasons,
                source_field,mapping_version,normalization_version,quality_policy_version
            ) VALUES (
                :match_id,:provider_id,:bookmaker,:market,:selection,:line,:decimal_odds,
                :identity,NULL,:role,'live_source','bookmaker','role_only','eligible',
                ARRAY['timestamp_semantics_unproven'],:source_field,
                'five_dfa_free_mapping_v1',:normalization_version,'five_dfa_free_quality_v1'
            )"""
        ),
        {
            "match_id": match_id,
            "provider_id": provider_id,
            "bookmaker": item.bookmaker,
            "market": item.market.value,
            "selection": item.selection.value,
            "line": item.line,
            "decimal_odds": item.decimal_odds,
            "identity": identity,
            "role": item.observation_role.value,
            "source_field": (
                f"{item.market.value}:{item.selection.value}:{item.observation_role.value}"
            ),
            "normalization_version": item.normalization_version,
        },
    )
    return True


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _day(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), time.min, UTC)


def _bounded_payloads(
    payloads: Sequence[Mapping[str, object]], max_fixtures: int | None
) -> tuple[dict[str, object], ...]:
    materialized = tuple(dict(item) for item in payloads)
    if max_fixtures is None:
        return materialized
    if max_fixtures <= 0:
        raise ValueError("max_fixtures must be positive")
    return tuple(
        sorted(
            materialized,
            key=lambda item: (str(item.get("kickoff_utc", "")), str(item.get("id", ""))),
        )[:max_fixtures]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist an authenticated internal shadow run")
    parser.add_argument("--start-date", required=True, type=_day)
    parser.add_argument("--end-date", required=True, type=_day)
    parser.add_argument("--as-of", required=True, type=_aware)
    parser.add_argument("--report-directory", required=True, type=Path)
    parser.add_argument("--verify-replay", action="store_true")
    parser.add_argument("--max-fixtures", type=int, default=8)
    args = parser.parse_args()
    settings = load_settings()
    config = load_five_dfa_project_config(os.environ)
    readiness_values = dict(os.environ)
    readiness_values["FIVEDFA_API_KEY"] = config.api_key
    readiness = evaluate_readiness(settings, readiness_values, provider_required=True)
    if not readiness.ready:
        raise RuntimeError("manual engine readiness failed")
    if not load_activation_gates(os.environ).safe_for_shadow:
        raise RuntimeError("manual shadow requires all production activation gates disabled")
    validate_report_root(args.report_directory)
    with FiveDfaClient(config) as client:
        adapter = FiveDfaFreeAdapter(client)
        if args.verify_replay:
            pair = run_persisted_shadow_with_replay(
                settings.database_url,
                adapter,
                start_time=args.start_date,
                end_time=args.end_date + timedelta(days=1),
                prediction_as_of=args.as_of,
                report_root=args.report_directory,
                max_fixtures=args.max_fixtures,
            )
            print(
                json.dumps(
                    {"first": _result_dict(pair.first), "replay": _result_dict(pair.replay)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        result = run_persisted_shadow(
            settings.database_url,
            adapter,
            start_time=args.start_date,
            end_time=args.end_date + timedelta(days=1),
            prediction_as_of=args.as_of,
            report_root=args.report_directory,
            max_fixtures=args.max_fixtures,
        )
    print(json.dumps(_result_dict(result), sort_keys=True, separators=(",", ":")))
    return 0


def _result_dict(result: PersistedShadowResult) -> dict[str, object]:
    output = result.report.to_dict()
    output["persisted_run_id"] = result.sync.run_id
    output["shadow_created"] = result.shadow_created
    output["shadow_reused"] = result.shadow_reused
    output["odds_created"] = result.odds_created
    output["odds_reused"] = result.odds_reused
    output["dq_created"] = result.dq_created
    output["report_directory"] = str(result.report_directory)
    return output


if __name__ == "__main__":
    raise SystemExit(main())
