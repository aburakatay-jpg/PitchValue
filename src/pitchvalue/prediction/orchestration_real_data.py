"""Read-only real-data adapter for TASK 20 historical policy simulation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, text

from pitchvalue.markets.edge import MarketEdgeResult
from pitchvalue.markets.edge_evaluation import (
    RawMLOOSRow,
    evaluate_market_value,
    generate_raw_ml_oos,
)
from pitchvalue.markets.history.market import load_historical_match_result_markets
from pitchvalue.ml.ensemble import ProbabilityModelPrediction
from pitchvalue.ml.ensemble_evaluation import EnsembleModelEvidence
from pitchvalue.ml.ensemble_real_data import load_real_ensemble_evidence
from pitchvalue.ml.real_data import load_real_match_result_dataset
from pitchvalue.models.signals import evaluate_match_result_agreement
from pitchvalue.models.signals.config import DEFAULT_SIGNAL_AGREEMENT_CONFIG, ModelFamily
from pitchvalue.models.signals.contracts import (
    DirectionalPreference,
    ModelSignal,
    SignalDiagnostic,
    SignalStatus,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection
from pitchvalue.prediction.orchestration import MatchDecision, orchestrate_match
from pitchvalue.prediction.orchestration_evaluation import (
    PolicySimulationSummary,
    summarize_policy_simulation,
)


@dataclass(frozen=True)
class RealOrchestrationEvaluation:
    raw_ml_oos_rows: int
    source_prematch: PolicySimulationSummary
    closing: PolicySimulationSummary


def load_real_orchestration_evaluation(
    connection: Connection,
) -> RealOrchestrationEvaluation:
    """Recreate accepted OOS evidence and evaluate both market roles without writes."""
    build = load_real_match_result_dataset(connection)
    oos = generate_raw_ml_oos(build.dataset)
    market = evaluate_market_value(
        oos,
        load_historical_match_result_markets(connection),
        competition_labels=build.competition_labels,
        season_labels=build.season_labels,
    )
    evidence = {
        item.row_id: item for item in load_real_ensemble_evidence(connection, build.dataset)
    }
    quality = _data_quality(connection)
    oos_by_id = {item.model.row_id: item for item in oos}
    prematch_decisions = _decisions(market.source_prematch.results, oos_by_id, evidence, quality)
    closing_decisions = _decisions(market.closing.results, oos_by_id, evidence, quality)
    return RealOrchestrationEvaluation(
        len(oos),
        summarize_policy_simulation(prematch_decisions, "ROLE_ONLY HISTORICAL POLICY SIMULATION"),
        summarize_policy_simulation(closing_decisions, "CLOSING REFERENCE POLICY DIAGNOSTIC"),
    )


def _decisions(
    results: tuple[MarketEdgeResult, ...],
    oos_by_id: dict[str, RawMLOOSRow],
    evidence_by_id: dict[str, EnsembleModelEvidence],
    quality: dict[str, tuple[Decimal | None, tuple[str, ...]]],
) -> tuple[MatchDecision, ...]:
    output = []
    for result in results:
        row: RawMLOOSRow = oos_by_id[result.row_id]
        evidence = evidence_by_id[result.row_id]
        signals = (
            _probability_signal(evidence.poisson, ModelFamily.POISSON, result.match_id),
            evidence.elo,
            evidence.form,
            _raw_ml_signal(row),
        )
        agreements = evaluate_match_result_agreement(signals, match_id=result.match_id)
        score, diagnostics = quality.get(
            result.match_id, (None, ("DATA_QUALITY_RECORD_UNAVAILABLE",))
        )
        output.append(
            orchestrate_match(
                result,
                agreements,
                signals,
                data_quality_score=score,
                data_quality_diagnostics=diagnostics,
                calibration_confidence=None,
                stability_score=None,
            )
        )
    return tuple(output)


def _raw_ml_signal(row: RawMLOOSRow) -> ModelSignal:
    prediction = max(
        row.model.probabilities,
        key=lambda item: (item.probability, -tuple(Selection).index(item.selection)),
    )
    return ModelSignal(
        ModelFamily.ML,
        row.model.model_version,
        row.model.match_id,
        MarketFamily.MATCH_RESULT,
        prediction.selection,
        _direction(prediction.selection),
        SignalStatus.READY,
        prediction.probability,
        probability=prediction.probability,
        raw_value=prediction.probability,
        diagnostics=(SignalDiagnostic("probability_source", "RAW_TASK16_ML"),),
    )


def _probability_signal(
    prediction: ProbabilityModelPrediction | None,
    family: ModelFamily,
    match_id: str,
) -> ModelSignal:
    if prediction is None:
        return ModelSignal(
            family,
            f"{family.value.lower()}-v1",
            match_id,
            MarketFamily.MATCH_RESULT,
            None,
            None,
            SignalStatus.ANALYSIS_UNAVAILABLE,
            None,
            diagnostics=(SignalDiagnostic("reason", "PROBABILITY_EVIDENCE_UNAVAILABLE"),),
        )
    ranked = tuple(
        sorted(prediction.probabilities, key=lambda item: item.probability, reverse=True)
    )
    if (
        ranked[0].probability - ranked[1].probability
        <= DEFAULT_SIGNAL_AGREEMENT_CONFIG.poisson_ambiguity_tolerance
    ):
        return ModelSignal(
            family,
            prediction.model_version,
            match_id,
            MarketFamily.MATCH_RESULT,
            None,
            None,
            SignalStatus.AMBIGUOUS,
            None,
            diagnostics=(SignalDiagnostic("reason", "PROBABILITY_SELECTION_AMBIGUOUS"),),
        )
    selected = ranked[0]
    return ModelSignal(
        family,
        prediction.model_version,
        match_id,
        MarketFamily.MATCH_RESULT,
        selected.selection,
        _direction(selected.selection),
        SignalStatus.READY,
        selected.probability,
        probability=selected.probability,
        raw_value=selected.probability,
        diagnostics=(SignalDiagnostic("residual_mass", prediction.unallocated_probability_mass),),
    )


def _direction(selection: Selection) -> DirectionalPreference | None:
    if selection is Selection.HOME:
        return DirectionalPreference.HOME
    if selection is Selection.AWAY:
        return DirectionalPreference.AWAY
    return None


def _data_quality(
    connection: Connection,
) -> dict[str, tuple[Decimal | None, tuple[str, ...]]]:
    rows = connection.execute(
        text(
            """
            SELECT match_id,quality_score,result_available,stats_available,
                   odds_available,xg_available,lineup_available,injury_available,
                   result_verified,cross_provider_verified
            FROM data_quality
            ORDER BY match_id
            """
        )
    ).mappings()
    result = {}
    for row in rows:
        score = row["quality_score"]
        diagnostics = (
            ("DATA_QUALITY_SCORE_UNAVAILABLE",)
            if score is None
            else tuple(
                name.upper()
                for name in (
                    "result_available",
                    "stats_available",
                    "odds_available",
                    "xg_available",
                    "lineup_available",
                    "injury_available",
                    "result_verified",
                    "cross_provider_verified",
                )
                if not row[name]
            )
        )
        result[str(row["match_id"])] = (score, diagnostics)
    return result
