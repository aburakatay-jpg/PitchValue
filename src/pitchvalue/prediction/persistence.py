"""Typed, deterministic mapping from TASK 20 outputs to persistence records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.markets.edge import EDGE_ENGINE_VERSION, NO_VIG_VERSION
from pitchvalue.ml.config import FeatureProfile
from pitchvalue.prediction.orchestration import MatchDecision, SelectionDecision


class PredictionPersistenceError(ValueError):
    """Raised when an orchestration output cannot be persisted without ambiguity."""


class PredictionRecordStatus(StrEnum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"


class PredictionWriteStatus(StrEnum):
    CREATED = "created"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass(frozen=True)
class PredictionIdentity:
    match_id: int
    prediction_as_of: datetime
    market: str
    selection: str
    probability_source: str
    model_version: str
    feature_profile: str
    orchestrator_version: str
    policy_version: str
    edge_engine_version: str
    no_vig_version: str
    bookmaker: str
    observation_role: str
    timing_semantics: str
    mapping_version: str
    normalization_version: str
    quality_policy_version: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PredictionIdentity:
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["prediction_as_of"] = datetime.fromisoformat(values["prediction_as_of"])
        return cls(**values)

    def parameters(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class PredictionPersistenceRequest:
    """One complete match result and the versions not carried by TASK 20 itself."""

    decision: MatchDecision
    generated_at: datetime
    feature_profile: str = FeatureProfile.FOOTBALL_PERFORMANCE_ONLY.value
    edge_engine_version: str = EDGE_ENGINE_VERSION
    no_vig_version: str = NO_VIG_VERSION
    bookmaker: str = "BET365"

    def __post_init__(self) -> None:
        _aware(self.generated_at, "generated_at")
        for name in ("feature_profile", "edge_engine_version", "no_vig_version", "bookmaker"):
            _nonblank(getattr(self, name), name)
        if not self.decision.selection_decisions:
            raise PredictionPersistenceError("a match write requires selection decisions")
        expected = (
            self.decision.match_id,
            self.decision.prediction_as_of,
            self.decision.orchestrator_version,
            self.decision.policy_version,
        )
        identities = {
            (
                item.match_id,
                item.prediction_as_of,
                item.orchestrator_version,
                item.policy_version,
            )
            for item in self.decision.selection_decisions
        }
        if identities != {expected}:
            raise PredictionPersistenceError("selection decisions do not share match identity")
        keys = {
            (item.market.value, item.selection.value) for item in self.decision.selection_decisions
        }
        if len(keys) != len(self.decision.selection_decisions):
            raise PredictionPersistenceError("duplicate market selection in match result")


@dataclass(frozen=True)
class PredictionWriteResult:
    status: PredictionWriteStatus
    created: int
    unchanged: int
    prediction_snapshot_ids: tuple[int, ...]


@dataclass(frozen=True)
class PersistedPrediction:
    prediction_snapshot_id: int
    match_id: int
    prediction_as_of: datetime
    generated_at: datetime
    persisted_at: datetime
    market: str
    selection: str
    model_probability: Decimal
    decimal_odds: Decimal
    no_vig_market_probability: Decimal
    edge: Decimal
    bet_score: Decimal | None
    bet_score_completeness: str
    score_class: str | None
    policy_decision: str
    publication_eligible: bool
    agreement_support_count: int
    agreement_usable_count: int
    agreement_configured_count: int
    agreement_status: str
    data_quality_score: Decimal | None
    data_quality_diagnostics: tuple[str, ...]
    poisson_status: str | None
    elo_status: str | None
    form_status: str | None
    blockers: tuple[str, ...]
    diagnostics: tuple[str, ...]
    components: tuple[dict[str, Any], ...]
    gates: tuple[dict[str, Any], ...]
    observation_role: str
    bookmaker: str
    timing_semantics: str
    market_observed_at: datetime | None
    comparison_status: str
    market_quality: str
    probability_source: str
    model_version: str
    feature_profile: str
    orchestrator_version: str
    policy_version: str
    edge_engine_version: str
    no_vig_version: str
    source_match_provider_ref_id: int
    source_staging_row_id: int
    source_field: str
    mapping_version: str
    normalization_version: str
    quality_policy_version: str
    record_status: PredictionRecordStatus
    invalidated_at: datetime | None
    invalidation_reason: str | None
    payload_hash: str

    @property
    def public_candidate(self) -> bool:
        return self.publication_eligible and self.record_status is PredictionRecordStatus.ACTIVE

    @property
    def identity(self) -> PredictionIdentity:
        return PredictionIdentity(
            **{name: getattr(self, name) for name in PredictionIdentity.__dataclass_fields__}
        )


def _nonblank(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PredictionPersistenceError(f"{name} must be nonblank")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PredictionPersistenceError(f"{name} must be timezone-aware")


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _component_payload(item: Any) -> dict[str, Any]:
    return {
        "name": item.name,
        "weight": str(item.weight),
        "status": item.status.value,
        "score": _decimal(item.score),
        "diagnostics": sorted(item.diagnostics),
    }


def _gate_payload(item: Any) -> dict[str, str]:
    return {"gate": item.gate.value, "status": item.status.value, "diagnostic": item.diagnostic}


def selection_payload(
    selection: SelectionDecision, request: PredictionPersistenceRequest
) -> dict[str, Any]:
    """Return the canonical semantic payload used both for storage and hashing."""
    lineage = selection.lineage
    return {
        "match_id": int(selection.match_id),
        "prediction_as_of": selection.prediction_as_of.isoformat(),
        "market": selection.market.value,
        "selection": selection.selection.value,
        "probability_source": selection.probability_source,
        "model_version": selection.model_version,
        "feature_profile": request.feature_profile,
        "orchestrator_version": selection.orchestrator_version,
        "policy_version": selection.policy_version,
        "edge_engine_version": request.edge_engine_version,
        "no_vig_version": request.no_vig_version,
        "bookmaker": request.bookmaker,
        "observation_role": selection.observation_role,
        "timing_semantics": selection.timing_semantics.value,
        "market_observed_at": (
            None if selection.observed_at is None else selection.observed_at.isoformat()
        ),
        "comparison_status": selection.comparison_status.value,
        "market_quality": selection.market_quality.value,
        "model_probability": str(selection.model_probability),
        "decimal_odds": str(selection.decimal_odds),
        "no_vig_market_probability": str(selection.no_vig_market_probability),
        "edge": str(selection.edge),
        "bet_score": _decimal(selection.bet_score),
        "bet_score_completeness": selection.bet_score_completeness.value,
        "score_class": None if selection.score_class is None else selection.score_class.value,
        "policy_decision": selection.policy_decision.value,
        "publication_eligible": selection.publication_eligible,
        "agreement_support_count": selection.agreement_support_count,
        "agreement_usable_count": selection.agreement_usable_count,
        "agreement_configured_count": selection.agreement_configured_count,
        "agreement_status": selection.agreement_status.value,
        "data_quality_score": _decimal(selection.data_quality_score),
        "poisson_status": None
        if selection.poisson_status is None
        else selection.poisson_status.value,
        "elo_status": None if selection.elo_status is None else selection.elo_status.value,
        "form_status": None if selection.form_status is None else selection.form_status.value,
        "components": sorted(
            (_component_payload(item) for item in selection.components),
            key=lambda item: item["name"],
        ),
        "gates": sorted(
            (_gate_payload(item) for item in selection.gates), key=lambda item: item["gate"]
        ),
        "blockers": sorted(selection.blockers),
        "diagnostics": sorted(selection.diagnostics),
        "data_quality_diagnostics": sorted(selection.data_quality_diagnostics),
        "source_match_provider_ref_id": lineage.source_match_provider_ref_id,
        "source_staging_row_id": lineage.source_staging_row_id,
        "source_field": lineage.source_field,
        "mapping_version": lineage.mapping_version,
        "normalization_version": lineage.normalization_version,
        "quality_policy_version": lineage.quality_policy_version,
    }


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
