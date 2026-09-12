"""Deterministic offline/read-only execution against canonical historical data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Connection, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.markets.edge import (
    MarketEdgeResult,
    build_market_probability,
    calculate_market_edges,
)
from pitchvalue.markets.edge_evaluation import RawMLOOSRow, generate_raw_ml_oos
from pitchvalue.markets.history.contracts import ObservationRole
from pitchvalue.markets.history.market import load_historical_match_result_markets
from pitchvalue.ml.contracts import RowStatus, TrainingRow
from pitchvalue.ml.ensemble_evaluation import EnsembleModelEvidence
from pitchvalue.ml.ensemble_real_data import load_real_ensemble_evidence
from pitchvalue.ml.real_data import load_real_match_result_dataset
from pitchvalue.models.signals import evaluate_match_result_agreement
from pitchvalue.models.signals.contracts import AgreementResult, ModelSignal
from pitchvalue.prediction.orchestration import MatchDecision
from pitchvalue.prediction.orchestration_real_data import (
    build_real_model_signals,
    orchestrate_real_market_results,
)

OFFLINE_VALIDATION_VERSION = "offline_historical_engine_validation_v1"
TIMESTAMP_GATE = "PENDING"
MARKET_STABILITY = "UNAVAILABLE"
FINAL_CHECK = "FINAL_CHECK_UNAVAILABLE"

_OPTIONAL_PROVIDER_FEATURES = (
    "CALIBRATION_CONFIDENCE",
    "CONFIRMED_LINEUPS",
    "FINAL_CHECK",
    "INJURIES_SUSPENSIONS",
    "MARKET_STABILITY",
    "MARKET_EXACT_TIMESTAMP",
)

_COUNT_TABLES = (
    "matches",
    "match_statistics",
    "teams",
    "team_aliases",
    "seasons",
    "data_quality",
    "football_data_staging_rows",
    "odds_snapshots",
    "prediction_snapshots",
    "engine_runs",
    "run_quarantines",
    "operational_events",
    "operational_event_deliveries",
    "data_quality_evaluations",
    "data_quality_evidence",
)


class OfflineDisposition(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    QUARANTINED = "QUARANTINED"
    ENGINE_FAILURE = "ENGINE_FAILURE"


class OfflineOddsMode(StrEnum):
    MODEL_ONLY = "MODEL_ONLY"
    MARKET_REFERENCE_ONLY = "MARKET_REFERENCE_ONLY"


@dataclass(frozen=True)
class OfflineAgreement:
    selection: str
    supporting_models: int
    usable_models: int
    configured_models: int


@dataclass(frozen=True)
class OfflineMatchResult:
    row_id: str
    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    prediction_as_of: datetime
    disposition: OfflineDisposition
    odds_mode: OfflineOddsMode
    dataset_status: RowStatus
    missing_feature_count: int
    statistics_available: bool
    leakage_safe: bool
    latest_source_kickoff: datetime | None
    raw_ml_probabilities: tuple[tuple[str, Decimal], ...]
    signal_statuses: tuple[tuple[str, str], ...]
    agreement: tuple[OfflineAgreement, ...]
    market_edges: tuple[tuple[str, Decimal], ...]
    bet_score_complete: bool
    publication_eligible: bool
    unavailable_features: tuple[str, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class OfflineValidationReport:
    validation_version: str
    execution_mode: str
    sample_size_requested: int
    canonical_rows: int
    ml_oos_rows: int
    evaluated_matches: int
    executable_matches: int
    insufficient_data_matches: int
    quarantined_matches: int
    unavailable_feature_cases: int
    engine_failures: int
    network_requests: int
    database_writes: int
    timestamp_gate: str
    market_stability: str
    final_check: str
    database_before: tuple[tuple[str, int], ...]
    database_after: tuple[tuple[str, int], ...]
    matches: tuple[OfflineMatchResult, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = _primitive(self)
        if not isinstance(payload, dict):  # pragma: no cover
            raise TypeError("offline validation report must serialize to a mapping")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload["fingerprint"] = hashlib.sha256(canonical.encode()).hexdigest()
        return payload


DecisionRunner = Callable[
    [
        Connection,
        tuple[MarketEdgeResult, ...],
        tuple[RawMLOOSRow, ...],
        tuple[EnsembleModelEvidence, ...],
    ],
    tuple[MatchDecision, ...],
]


def run_offline_validation(
    connection: Connection,
    *,
    sample_size: int = 12,
    decision_runner: DecisionRunner = orchestrate_real_market_results,
) -> OfflineValidationReport:
    """Execute a deterministic historical sample in the caller's read-only transaction."""
    if sample_size < 1 or sample_size > 100:
        raise ValueError("sample_size must be between 1 and 100")
    if connection.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
        raise RuntimeError("offline validation requires a database-enforced read-only transaction")
    before = _database_counts(connection)
    build = load_real_match_result_dataset(connection)
    oos = generate_raw_ml_oos(build.dataset)
    oos_by_id = {item.model.row_id: item for item in oos}
    stats = _statistics_availability(connection)
    selected = _select_rows(build.dataset.rows, frozenset(oos_by_id), stats, sample_size)
    leakage = {row.row_id: _leakage_audit(row) for row in selected}
    executable_ids = frozenset(
        row.row_id for row in selected if row.row_id in oos_by_id and leakage[row.row_id][0]
    )
    evidence = load_real_ensemble_evidence(connection, build.dataset, row_ids=executable_ids)
    evidence_by_id = {item.row_id: item for item in evidence}
    markets = load_historical_match_result_markets(connection)
    prematch = {
        item.match_id: item
        for item in markets.groups
        if item.observation_role is ObservationRole.SOURCE_PREMATCH
    }

    results: list[OfflineMatchResult] = []
    for row in selected:
        audit_safe, latest_source = leakage[row.row_id]
        missing = sum(feature.value is None for feature in row.features)
        unavailable = list(_OPTIONAL_PROVIDER_FEATURES)
        diagnostics: list[str] = []
        if not stats.get(row.match_id, False):
            unavailable.append("MATCH_STATISTICS")
            diagnostics.append("MATCH_STATISTICS_UNAVAILABLE_OPTIONAL")
        if not audit_safe:
            results.append(
                _empty_result(
                    row,
                    OfflineDisposition.QUARANTINED,
                    stats.get(row.match_id, False),
                    missing,
                    latest_source,
                    tuple(unavailable),
                    ("HISTORICAL_LEAKAGE_DETECTED",),
                )
            )
            continue
        oos_row = oos_by_id.get(row.row_id)
        if oos_row is None:
            results.append(
                _empty_result(
                    row,
                    OfflineDisposition.INSUFFICIENT_DATA,
                    stats.get(row.match_id, False),
                    missing,
                    latest_source,
                    tuple(unavailable),
                    ("TEMPORAL_OOS_MODEL_EVIDENCE_UNAVAILABLE", *diagnostics),
                )
            )
            continue

        model_evidence = evidence_by_id[oos_row.model.row_id]
        signals: tuple[ModelSignal, ...] = ()
        agreements: tuple[AgreementResult, ...] = ()
        edge_result: MarketEdgeResult | None = None
        odds_mode = OfflineOddsMode.MODEL_ONLY
        try:
            signals = build_real_model_signals(oos_row, model_evidence)
            agreements = evaluate_match_result_agreement(signals, match_id=row.match_id)
            group = prematch.get(row.match_id)
            if group is not None:
                edge_result = calculate_market_edges(oos_row.model, build_market_probability(group))
                odds_mode = OfflineOddsMode.MARKET_REFERENCE_ONLY
            else:
                unavailable.append("MARKET_REFERENCE")
            decisions = (
                decision_runner(connection, (edge_result,), (oos_row,), (model_evidence,))
                if edge_result is not None
                else ()
            )
        except Exception as exc:  # isolated match failure must not corrupt the sample
            results.append(
                _engine_failure_result(
                    row,
                    oos_row,
                    signals,
                    agreements,
                    edge_result,
                    stats.get(row.match_id, False),
                    missing,
                    latest_source,
                    tuple(unavailable),
                    type(exc).__name__,
                )
            )
            continue
        decision = decisions[0] if decisions else None
        if decision is not None and decision.publication_eligible:
            raise RuntimeError("offline validation must never produce publication-eligible output")
        results.append(
            _successful_result(
                row,
                oos_row,
                signals,
                agreements,
                edge_result,
                decision,
                odds_mode,
                stats.get(row.match_id, False),
                missing,
                latest_source,
                tuple(unavailable),
                tuple(diagnostics),
            )
        )

    ordered = tuple(sorted(results, key=lambda item: (item.kickoff, item.row_id)))
    dispositions = Counter(item.disposition for item in ordered)
    after = _database_counts(connection)
    if before != after:
        raise RuntimeError("offline validation changed protected database counts")
    return OfflineValidationReport(
        OFFLINE_VALIDATION_VERSION,
        "OFFLINE_READ_ONLY",
        sample_size,
        len(build.dataset.rows),
        len(oos),
        len(ordered),
        dispositions[OfflineDisposition.EXECUTABLE],
        dispositions[OfflineDisposition.INSUFFICIENT_DATA],
        dispositions[OfflineDisposition.QUARANTINED],
        sum(bool(item.unavailable_features) for item in ordered),
        dispositions[OfflineDisposition.ENGINE_FAILURE],
        0,
        0,
        TIMESTAMP_GATE,
        MARKET_STABILITY,
        FINAL_CHECK,
        before,
        after,
        ordered,
    )


def _select_rows(
    rows: tuple[TrainingRow, ...],
    oos_ids: frozenset[str],
    statistics: dict[str, bool],
    limit: int,
) -> tuple[TrainingRow, ...]:
    ordered = tuple(sorted(rows, key=lambda row: (row.kickoff, row.row_id)))
    selected: list[TrainingRow] = []

    def add(row: TrainingRow | None) -> None:
        if row is not None and row not in selected and len(selected) < limit:
            selected.append(row)

    add(next((row for row in ordered if row.row_id not in oos_ids), None))
    add(next((row for row in ordered if not statistics.get(row.match_id, False)), None))
    for competition in sorted({row.competition_id for row in ordered}):
        add(
            next(
                (
                    row
                    for row in ordered
                    if row.competition_id == competition and row.row_id in oos_ids
                ),
                None,
            )
        )
    for row in ordered:
        if len(selected) >= limit:
            break
        if row.row_id in oos_ids:
            add(row)
    return tuple(sorted(selected, key=lambda row: (row.kickoff, row.row_id)))


def _leakage_audit(row: TrainingRow) -> tuple[bool, datetime | None]:
    safe = row.prediction_as_of < row.kickoff
    source_kickoffs: list[datetime] = []
    for feature in row.features:
        safe = safe and feature.available_at <= row.prediction_as_of
        for source in feature.provenance.source_matches:
            source_kickoffs.append(source.kickoff)
            safe = (
                safe and source.kickoff < row.prediction_as_of and source.match_id != row.match_id
            )
        safe = safe and not feature.provenance.contains_target_result
        safe = safe and not feature.provenance.contains_target_goals
    return safe, max(source_kickoffs) if source_kickoffs else None


def _successful_result(
    row: TrainingRow,
    oos: RawMLOOSRow,
    signals: tuple[ModelSignal, ...],
    agreements: tuple[AgreementResult, ...],
    edge: MarketEdgeResult | None,
    decision: MatchDecision | None,
    odds_mode: OfflineOddsMode,
    statistics_available: bool,
    missing: int,
    latest_source: datetime | None,
    unavailable: tuple[str, ...],
    diagnostics: tuple[str, ...],
) -> OfflineMatchResult:
    return OfflineMatchResult(
        row.row_id,
        row.match_id,
        row.competition_id,
        row.season_id,
        row.kickoff,
        row.prediction_as_of,
        OfflineDisposition.EXECUTABLE,
        odds_mode,
        row.status,
        missing,
        statistics_available,
        True,
        latest_source,
        tuple((item.selection.value, item.probability) for item in oos.model.probabilities),
        tuple((item.model_family.value, item.signal_status.value) for item in signals),
        tuple(
            OfflineAgreement(
                item.candidate_selection.value,
                item.supporting_model_count,
                item.usable_model_count,
                item.configured_model_count,
            )
            for item in agreements
        ),
        tuple((item.selection.value, item.edge) for item in edge.edges) if edge else (),
        bool(
            decision
            and all(
                item.bet_score_completeness.value == "COMPLETE"
                for item in decision.selection_decisions
            )
        ),
        False,
        tuple(sorted(set(unavailable))),
        tuple(sorted(set(diagnostics))),
    )


def _empty_result(
    row: TrainingRow,
    disposition: OfflineDisposition,
    statistics_available: bool,
    missing: int,
    latest_source: datetime | None,
    unavailable: tuple[str, ...],
    diagnostics: tuple[str, ...],
) -> OfflineMatchResult:
    return OfflineMatchResult(
        row.row_id,
        row.match_id,
        row.competition_id,
        row.season_id,
        row.kickoff,
        row.prediction_as_of,
        disposition,
        OfflineOddsMode.MODEL_ONLY,
        row.status,
        missing,
        statistics_available,
        disposition is not OfflineDisposition.QUARANTINED,
        latest_source,
        (),
        (),
        (),
        (),
        False,
        False,
        tuple(sorted(set(unavailable))),
        tuple(sorted(set(diagnostics))),
    )


def _engine_failure_result(
    row: TrainingRow,
    oos: RawMLOOSRow,
    signals: tuple[ModelSignal, ...],
    agreements: tuple[AgreementResult, ...],
    edge: MarketEdgeResult | None,
    statistics_available: bool,
    missing: int,
    latest_source: datetime | None,
    unavailable: tuple[str, ...],
    exception_name: str,
) -> OfflineMatchResult:
    base = _successful_result(
        row,
        oos,
        signals,
        agreements,
        edge,
        None,
        OfflineOddsMode.MARKET_REFERENCE_ONLY if edge else OfflineOddsMode.MODEL_ONLY,
        statistics_available,
        missing,
        latest_source,
        unavailable,
        (f"ENGINE_EXCEPTION:{exception_name}",),
    )
    return replace(base, disposition=OfflineDisposition.ENGINE_FAILURE)


def _statistics_availability(connection: Connection) -> dict[str, bool]:
    rows = connection.execute(
        text(
            """
            SELECT m.match_id, (ms.match_id IS NOT NULL) AS statistics_available
            FROM matches m
            LEFT JOIN match_statistics ms ON ms.match_id=m.match_id
            ORDER BY m.match_id
            """
        )
    ).mappings()
    return {str(row["match_id"]): bool(row["statistics_available"]) for row in rows}


def _database_counts(connection: Connection) -> tuple[tuple[str, int], ...]:
    return tuple(
        (table, int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()))
        for table in _COUNT_TABLES
    )


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic offline historical validation")
    parser.add_argument("--sample-size", type=int, default=12)
    arguments = parser.parse_args()
    engine = create_engine(load_settings().database_url, pool_pre_ping=True)
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            report = run_offline_validation(connection, sample_size=arguments.sample_size)
            print(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
