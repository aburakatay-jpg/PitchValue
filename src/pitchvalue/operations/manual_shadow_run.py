"""Authenticated zero-cost 5DFA shadow execution with read-only canonical data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.features.contracts import TargetFixture
from pitchvalue.ingestion.football_data_uk.canonical import normalize_team_name
from pitchvalue.ml.model import fit_multinomial_logistic, predict_multinomial_logistic
from pitchvalue.ml.real_data import (
    build_live_prediction_evidence,
    load_real_match_result_dataset,
)
from pitchvalue.models.form import analyze_form_signal
from pitchvalue.models.poisson import analyze_poisson, input_from_match_features
from pitchvalue.models.signals import (
    adapt_elo_signal,
    adapt_form_signal,
    adapt_poisson_signal,
    evaluate_match_result_agreement,
)
from pitchvalue.models.signals.config import ModelFamily
from pitchvalue.models.signals.contracts import (
    DirectionalPreference,
    ModelSignal,
    SignalStatus,
)
from pitchvalue.operations.events import EventType
from pitchvalue.prediction.contracts import MarketFamily, Selection
from pitchvalue.providers.five_dfa.adapter import FiveDfaFreeAdapter
from pitchvalue.providers.five_dfa.capabilities import FREE_CAPABILITIES, PROVIDER_NAME
from pitchvalue.providers.five_dfa.client import FiveDfaClient
from pitchvalue.providers.five_dfa.config import load_five_dfa_project_config
from pitchvalue.providers.five_dfa.fixtures import (
    FixtureStatus,
    ProviderFixture,
    build_sync_plan,
    parse_runtime_fixture,
)
from pitchvalue.providers.five_dfa.mapping import MappingStatus
from pitchvalue.providers.five_dfa.odds import normalize_bet365_snapshot

SHADOW_RUN_VERSION = "five_dfa_authenticated_shadow_run_v1"
TIMESTAMP_GATE = "PENDING"
MARKET_STABILITY = "UNAVAILABLE"
FINAL_CHECK = "FINAL_CHECK_UNAVAILABLE"
LIVE_SEASON_ID = "live-2026-27"

_COUNT_TABLES = (
    "matches",
    "match_statistics",
    "teams",
    "team_aliases",
    "seasons",
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


class ShadowOddsMode(StrEnum):
    MODEL_ONLY = "MODEL_ONLY"
    MARKET_REFERENCE_ONLY = "MARKET_REFERENCE_ONLY"
    EXACT_TIME_MARKET = "EXACT_TIME_MARKET"


class GateStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class ShadowFixtureResult:
    provider_fixture_id: str
    competition: str | None
    kickoff: datetime
    home_team: str
    away_team: str
    home_team_id: int | None
    away_team_id: int | None
    gate_status: GateStatus
    reasons: tuple[str, ...]
    raw_ml_probabilities: tuple[tuple[str, Decimal], ...] = ()
    model_statuses: tuple[tuple[str, str], ...] = ()
    agreement_count: int = 0
    odds_mode: ShadowOddsMode = ShadowOddsMode.MODEL_ONLY
    provider_markets: tuple[str, ...] = ()
    market_observed_at: None = None
    bet_score: None = None
    publication_eligible: bool = False
    history_rows: int = 0
    latest_source_kickoff: datetime | None = None


@dataclass(frozen=True)
class AuthenticatedShadowRunReport:
    run_version: str
    run_id: str
    provider: str
    plan: str
    start_time: datetime
    end_time: datetime
    prediction_as_of: datetime
    execution_mode: str
    fixture_requests: int
    odds_requests: int
    request_ids_supplied: int
    rate_limit_limit: int | None
    rate_limit_remaining: int | None
    provider_rows: int
    eligible: int
    quarantined: int
    quarantine_reasons: tuple[tuple[str, int], ...]
    model_counts: tuple[tuple[str, int], ...]
    odds_mode_counts: tuple[tuple[str, int], ...]
    refresh_counts: tuple[tuple[str, int], ...]
    timestamp_gate: str
    market_stability: str
    final_check: str
    calibration_confidence: str
    bet_score_complete: int
    bet_score_null: int
    database_before: tuple[tuple[str, int], ...]
    database_after: tuple[tuple[str, int], ...]
    database_writes: int
    public_eligible_predictions: int
    sync_write_status: str
    operational_events: tuple[str, ...]
    fixtures: tuple[ShadowFixtureResult, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = _primitive(self)
        if not isinstance(payload, dict):  # pragma: no cover
            raise TypeError("shadow report must serialize to an object")
        semantic = dict(payload)
        # Quota telemetry is expected to change between otherwise identical authenticated
        # replays. It remains visible in the report but cannot alter the analysis identity.
        semantic.pop("rate_limit_remaining", None)
        semantic.pop("request_ids_supplied", None)
        canonical = json.dumps(semantic, sort_keys=True, separators=(",", ":"))
        payload["fingerprint"] = hashlib.sha256(canonical.encode()).hexdigest()
        return payload


def run_authenticated_shadow(
    connection: Connection,
    adapter: FiveDfaFreeAdapter,
    *,
    start_time: datetime,
    end_time: datetime,
    prediction_as_of: datetime,
) -> AuthenticatedShadowRunReport:
    """Fetch authentic fixtures while PostgreSQL enforces a read-only transaction."""
    if connection.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
        raise RuntimeError("authenticated shadow execution requires a read-only transaction")
    if not (start_time.tzinfo and end_time.tzinfo and prediction_as_of.tzinfo):
        raise ValueError("shadow timestamps must be timezone-aware")
    if end_time <= start_time or end_time - start_time > timedelta(days=1):
        raise ValueError("fixture window must be positive and at most 24 hours")
    before = _database_counts(connection)
    payloads, rate_states = adapter.fixture_payloads(start_time=start_time, end_time=end_time)
    team_mappings = _explicit_team_mappings(connection, payloads)
    parsed: list[ProviderFixture] = []
    errors: list[str] = []
    for payload in payloads:
        try:
            parsed.append(parse_runtime_fixture(payload, explicit_team_mappings=team_mappings))
        except ValueError as exc:
            errors.append(f"FIXTURE_PAYLOAD_INVALID:{type(exc).__name__}")
    parsed.sort(key=lambda item: (item.kickoff_utc, item.provider_fixture_id))
    plan = build_sync_plan(tuple(parsed), ())
    contexts = _competition_contexts(connection)
    dataset = load_real_match_result_dataset(connection)
    training = tuple(row for row in dataset.dataset.rows if row.prediction_as_of < prediction_as_of)
    model = fit_multinomial_logistic(training)
    if model is None:
        raise RuntimeError("RAW ML training evidence is insufficient")

    results: list[ShadowFixtureResult] = []
    odds_requests = 0
    model_counts: Counter[str] = Counter()
    for fixture in parsed:
        reasons = _gate_reasons(fixture, prediction_as_of, contexts)
        if reasons:
            results.append(_quarantined(fixture, reasons))
            continue
        assert fixture.competition.canonical_name is not None
        assert fixture.home_team.canonical_team_id is not None
        assert fixture.away_team.canonical_team_id is not None
        competition_id, previous_season_id = contexts[fixture.competition.canonical_name]
        target = TargetFixture(
            f"five-dfa:{fixture.provider_fixture_id}",
            str(competition_id),
            LIVE_SEASON_ID,
            fixture.kickoff_utc,
            str(fixture.home_team.canonical_team_id),
            str(fixture.away_team.canonical_team_id),
            prediction_as_of,
        )
        try:
            evidence = build_live_prediction_evidence(
                connection, target, previous_season_id=str(previous_season_id)
            )
            if evidence.history_rows == 0:
                raise ValueError("historical context unavailable")
            if any(
                feature.available_at > prediction_as_of
                or any(
                    source.kickoff >= prediction_as_of
                    for source in feature.provenance.source_matches
                )
                for feature in evidence.row.features
            ):
                raise RuntimeError("future feature evidence detected")
            ml_prediction = predict_multinomial_logistic(model, (evidence.row,))[0]
            poisson = analyze_poisson(input_from_match_features(evidence.features))
            form = analyze_form_signal(evidence.features)
            signals = (
                _ml_signal(ml_prediction, target.match_id),
                adapt_elo_signal(evidence.elo),
                adapt_poisson_signal(poisson),
                adapt_form_signal(form),
            )
            agreements = evaluate_match_result_agreement(signals, match_id=target.match_id)
            for signal in signals:
                if signal.signal_status is SignalStatus.READY:
                    model_counts[signal.model_family.value] += 1
            model_counts["AGREEMENT"] += int(bool(agreements))
            odds_mode = ShadowOddsMode.MODEL_ONLY
            provider_markets: tuple[str, ...] = ()
            try:
                odds_requests += 1
                normalized = normalize_bet365_snapshot(
                    adapter.fixture_odds_payload(fixture.provider_fixture_id)
                )
                provider_markets = tuple(
                    sorted({item.market.value for item in normalized.observations})
                )
                if normalized.observations:
                    odds_mode = ShadowOddsMode.MARKET_REFERENCE_ONLY
            except Exception as exc:  # model-only degradation is deliberate
                errors.append(
                    f"ODDS_UNAVAILABLE:{fixture.provider_fixture_id}:{type(exc).__name__}"
                )
            results.append(
                ShadowFixtureResult(
                    fixture.provider_fixture_id,
                    fixture.competition.canonical_name,
                    fixture.kickoff_utc,
                    fixture.home_team.provider_name,
                    fixture.away_team.provider_name,
                    fixture.home_team.canonical_team_id,
                    fixture.away_team.canonical_team_id,
                    GateStatus.ELIGIBLE,
                    (),
                    tuple(
                        (item.selection.value, item.probability)
                        for item in ml_prediction.probabilities
                    ),
                    tuple((item.model_family.value, item.signal_status.value) for item in signals),
                    len(agreements),
                    odds_mode,
                    provider_markets,
                    history_rows=evidence.history_rows,
                    latest_source_kickoff=evidence.latest_source_kickoff,
                )
            )
        except Exception as exc:
            results.append(
                _quarantined(fixture, (f"ENGINE_INPUT_UNAVAILABLE:{type(exc).__name__}",))
            )

    results.sort(key=lambda item: (item.kickoff, item.provider_fixture_id))
    after = _database_counts(connection)
    if before != after:
        raise RuntimeError("authenticated shadow execution changed protected database counts")
    reason_counts = Counter(reason for item in results for reason in item.reasons)
    mode_counts = Counter(
        item.odds_mode.value for item in results if item.gate_status is GateStatus.ELIGIBLE
    )
    refresh_counts = Counter(item.action.value for item in plan.refreshes)
    rate_limit = rate_states[-1] if rate_states else None
    identity = "|".join(
        [
            SHADOW_RUN_VERSION,
            start_time.isoformat(),
            end_time.isoformat(),
            prediction_as_of.isoformat(),
            *(item.provider_fixture_id for item in results),
        ]
    )
    run_id = "shadow-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
    return AuthenticatedShadowRunReport(
        SHADOW_RUN_VERSION,
        run_id,
        PROVIDER_NAME,
        FREE_CAPABILITIES.plan_name,
        start_time,
        end_time,
        prediction_as_of,
        "AUTHENTICATED_READ_ONLY_DRY_RUN",
        len(rate_states),
        odds_requests,
        0,
        rate_limit.limit if rate_limit else None,
        rate_limit.remaining if rate_limit else None,
        len(payloads),
        sum(item.gate_status is GateStatus.ELIGIBLE for item in results),
        sum(item.gate_status is GateStatus.QUARANTINED for item in results),
        tuple(sorted(reason_counts.items())),
        tuple(sorted(model_counts.items())),
        tuple(sorted(mode_counts.items())),
        tuple(sorted(refresh_counts.items())),
        TIMESTAMP_GATE,
        MARKET_STABILITY,
        FINAL_CHECK,
        "UNAVAILABLE",
        0,
        sum(item.gate_status is GateStatus.ELIGIBLE for item in results),
        before,
        after,
        0,
        0,
        "DRY_RUN_LIVE_SYNC_WRITE_PATH_UNAVAILABLE",
        (
            EventType.RUN_STARTED.value,
            EventType.CURRENT_SEASON_SYNC_STARTED.value,
            EventType.CURRENT_SEASON_SYNC_SUCCEEDED.value,
            EventType.FIXTURE_REFRESH_STARTED.value,
            EventType.FIXTURE_REFRESH_SUCCEEDED.value,
            EventType.DATA_GATE_STARTED.value,
            EventType.DATA_GATE_SUCCEEDED.value,
            EventType.FULL_ENGINE_STARTED.value,
            EventType.MATCH_ANALYSIS_COMPLETED.value,
            EventType.REPORT_GENERATION_STARTED.value,
            EventType.REPORT_GENERATION_SUCCEEDED.value,
            EventType.RUN_SUCCEEDED.value,
        ),
        tuple(results),
        tuple(sorted(errors)),
    )


def write_local_reports(report: AuthenticatedShadowRunReport, root: Path) -> Path:
    """Write deterministic, secret-free operator artifacts outside canonical storage."""
    directory = root / str(report.start_time.year) / report.run_id
    directory.mkdir(parents=True, exist_ok=True)
    _write_json(directory / "run-summary.json", report.to_dict())
    _write_csv(
        directory / "fixtures.csv",
        (
            {
                "provider_fixture_id": item.provider_fixture_id,
                "competition": item.competition,
                "kickoff": item.kickoff.isoformat(),
                "home_team": item.home_team,
                "away_team": item.away_team,
                "gate_status": item.gate_status.value,
                "reasons": ";".join(item.reasons),
            }
            for item in report.fixtures
        ),
    )
    _write_csv(
        directory / "predictions.csv",
        (
            {
                "provider_fixture_id": item.provider_fixture_id,
                "selection": selection,
                "raw_ml_probability": str(probability),
                "publication_eligible": "false",
            }
            for item in report.fixtures
            for selection, probability in item.raw_ml_probabilities
        ),
    )
    _write_csv(
        directory / "market-evaluations.csv",
        (
            {
                "provider_fixture_id": item.provider_fixture_id,
                "odds_mode": item.odds_mode.value,
                "markets": ";".join(item.provider_markets),
                "market_observed_at": "",
                "edge_available": "false",
            }
            for item in report.fixtures
        ),
    )
    _write_csv(
        directory / "data-quality.csv",
        (
            {
                "provider_fixture_id": item.provider_fixture_id,
                "status": item.gate_status.value,
                "history_rows": item.history_rows,
                "latest_source_kickoff": item.latest_source_kickoff.isoformat()
                if item.latest_source_kickoff
                else "",
            }
            for item in report.fixtures
        ),
    )
    _write_csv(
        directory / "quarantined-matches.csv",
        (
            {
                "provider_fixture_id": item.provider_fixture_id,
                "reasons": ";".join(item.reasons),
            }
            for item in report.fixtures
            if item.gate_status is GateStatus.QUARANTINED
        ),
    )
    _write_json(directory / "errors.json", {"errors": list(report.errors)})
    return directory


def _explicit_team_mappings(
    connection: Connection, payloads: Iterable[Mapping[str, object]]
) -> dict[str, int]:
    names: dict[str, set[int]] = defaultdict(set)
    rows = connection.execute(
        text(
            """
            SELECT team_id, normalized_name FROM teams
            UNION ALL
            SELECT team_id, normalized_alias FROM team_aliases
            """
        )
    )
    for team_id, normalized in rows:
        names[str(normalized)].add(int(team_id))
    result: dict[str, int] = {}
    for payload in payloads:
        teams = payload.get("teams")
        if not isinstance(teams, dict):
            continue
        for side in ("home", "away"):
            team = teams.get(side)
            if not isinstance(team, dict):
                continue
            provider_id = team.get("id")
            provider_name = team.get("name")
            if isinstance(provider_id, (str, int)) and isinstance(provider_name, str):
                matches = names.get(normalize_team_name(provider_name), set())
                if len(matches) == 1:
                    result[str(provider_id)] = next(iter(matches))
    return result


def _competition_contexts(connection: Connection) -> dict[str, tuple[int, int]]:
    rows = connection.execute(
        text(
            """
            SELECT c.canonical_name,c.competition_id,s.season_id
            FROM competitions c
            JOIN seasons s ON s.competition_id=c.competition_id
            WHERE s.season_name='2025/26'
            """
        )
    )
    return {
        str(name): (int(competition_id), int(season_id)) for name, competition_id, season_id in rows
    }


def _gate_reasons(
    fixture: ProviderFixture,
    prediction_as_of: datetime,
    contexts: Mapping[str, tuple[int, int]],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if fixture.competition.status is not MappingStatus.RESOLVED:
        reasons.append("UNSUPPORTED_COMPETITION")
    if fixture.home_team.status is not MappingStatus.RESOLVED:
        reasons.append("HOME_TEAM_MAPPING_UNRESOLVED")
    if fixture.away_team.status is not MappingStatus.RESOLVED:
        reasons.append("AWAY_TEAM_MAPPING_UNRESOLVED")
    if fixture.status is not FixtureStatus.SCHEDULED:
        reasons.append(f"FIXTURE_STATUS_{fixture.status.value.upper()}")
    if fixture.kickoff_utc <= prediction_as_of:
        reasons.append("FIXTURE_NOT_UPCOMING")
    canonical = fixture.competition.canonical_name
    if canonical is not None and canonical not in contexts:
        reasons.append("PREVIOUS_SEASON_CONTEXT_UNAVAILABLE")
    if canonical is not None and canonical not in (
        "Premier League",
        "Ligue 1",
        "Bundesliga",
        "La Liga",
    ):
        reasons.append("UNAUTHORIZED_COMPETITION")
    return tuple(sorted(set(reasons)))


def _quarantined(fixture: ProviderFixture, reasons: tuple[str, ...]) -> ShadowFixtureResult:
    return ShadowFixtureResult(
        fixture.provider_fixture_id,
        fixture.competition.canonical_name,
        fixture.kickoff_utc,
        fixture.home_team.provider_name,
        fixture.away_team.provider_name,
        fixture.home_team.canonical_team_id,
        fixture.away_team.canonical_team_id,
        GateStatus.QUARANTINED,
        tuple(sorted(set(reasons))),
    )


def _ml_signal(prediction: object, match_id: str) -> ModelSignal:
    from pitchvalue.ml.model import MLPrediction

    if not isinstance(prediction, MLPrediction):
        raise TypeError("RAW ML prediction contract required")
    selected = max(prediction.probabilities, key=lambda item: item.probability)
    direction = (
        DirectionalPreference.HOME
        if selected.selection is Selection.HOME
        else DirectionalPreference.AWAY
        if selected.selection is Selection.AWAY
        else None
    )
    return ModelSignal(
        ModelFamily.ML,
        prediction.model_version,
        match_id,
        MarketFamily.MATCH_RESULT,
        selected.selection,
        direction,
        SignalStatus.READY,
        selected.probability,
        probability=selected.probability,
        raw_value=selected.probability,
    )


def _database_counts(connection: Connection) -> tuple[tuple[str, int], ...]:
    return tuple(
        (table, int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()))
        for table in _COUNT_TABLES
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    materialized = list(rows)
    if not materialized:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(materialized[0]))
        writer.writeheader()
        writer.writerows(materialized)


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


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _day_start(value: str) -> datetime:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc
    return datetime.combine(parsed, time.min, UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run authenticated read-only 5DFA shadow analysis")
    parser.add_argument("--start-date", required=True, type=_day_start)
    parser.add_argument("--end-date", required=True, type=_day_start)
    parser.add_argument("--as-of", required=True, type=_aware)
    parser.add_argument("--report-directory", required=True, type=Path)
    arguments = parser.parse_args()
    start = arguments.start_date
    end = arguments.end_date + timedelta(days=1)
    config = load_five_dfa_project_config(os.environ)
    engine = create_engine(load_settings().database_url, pool_pre_ping=True)
    try:
        with FiveDfaClient(config) as client:
            adapter = FiveDfaFreeAdapter(client)
            with engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                report = run_authenticated_shadow(
                    connection,
                    adapter,
                    start_time=start,
                    end_time=end,
                    prediction_as_of=arguments.as_of,
                )
        directory = write_local_reports(report, arguments.report_directory)
        output = report.to_dict()
        output["report_directory"] = str(directory)
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
