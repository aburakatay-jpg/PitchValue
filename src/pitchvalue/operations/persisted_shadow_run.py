"""Authenticated current-season persistence followed by internal shadow analysis."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations.current_season import (
    CurrentSeasonPersistenceResult,
    deterministic_run_id,
    persist_current_season_payloads,
)
from pitchvalue.operations.manual_shadow_run import (
    AuthenticatedShadowRunReport,
    GateStatus,
    run_authenticated_shadow,
    write_local_reports,
)
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
) -> PersistedShadowResult:
    """Persist authentic source evidence and never-public shadow analysis replay-safely."""
    payloads, rate_states = adapter.fixture_payloads(start_time=start_time, end_time=end_time)
    materialized = tuple(dict(item) for item in payloads)
    run_id = deterministic_run_id(materialized, prediction_as_of)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            sync = persist_current_season_payloads(
                connection,
                materialized,
                run_id=run_id,
                window_start=start_time,
                window_end=end_time,
                prediction_as_of=prediction_as_of,
            )
        replay = _ReplayAdapter(materialized, rate_states, adapter)
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
                        run_id,
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
                            match_id, run_id, prediction_as_of, fixture.history_rows
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
    finally:
        engine.dispose()


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
    created = connection.execute(
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
            ) ON CONFLICT (provider_id,provider_market_id,normalization_version)
            WHERE observation_origin='live_source' AND provider_id IS NOT NULL
              AND provider_market_id IS NOT NULL AND normalization_version IS NOT NULL
            DO NOTHING RETURNING odds_snapshot_id"""
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
    ).scalar_one_or_none()
    if created is not None:
        return True
    existing = connection.execute(
        text(
            """SELECT decimal_odds FROM odds_snapshots
            WHERE provider_id=:provider_id AND provider_market_id=:identity
              AND normalization_version=:normalization_version
              AND observation_origin='live_source'"""
        ),
        {
            "provider_id": provider_id,
            "identity": identity,
            "normalization_version": item.normalization_version,
        },
    ).scalar_one()
    if existing != item.decimal_odds:
        raise ValueError("live odds identity has a conflicting role-only price")
    return False


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _day(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), time.min, UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist an authenticated internal shadow run")
    parser.add_argument("--start-date", required=True, type=_day)
    parser.add_argument("--end-date", required=True, type=_day)
    parser.add_argument("--as-of", required=True, type=_aware)
    parser.add_argument("--report-directory", required=True, type=Path)
    args = parser.parse_args()
    config = load_five_dfa_project_config(os.environ)
    with FiveDfaClient(config) as client:
        result = run_persisted_shadow(
            load_settings().database_url,
            FiveDfaFreeAdapter(client),
            start_time=args.start_date,
            end_time=args.end_date + timedelta(days=1),
            prediction_as_of=args.as_of,
            report_root=args.report_directory,
        )
    output = result.report.to_dict()
    output["persisted_run_id"] = result.sync.run_id
    output["shadow_created"] = result.shadow_created
    output["shadow_reused"] = result.shadow_reused
    output["odds_created"] = result.odds_created
    output["odds_reused"] = result.odds_reused
    output["dq_created"] = result.dq_created
    output["report_directory"] = str(result.report_directory)
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
