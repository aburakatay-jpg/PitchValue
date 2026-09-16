"""Public-evidence-only AI and deterministic coupon execution contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pitchvalue.prediction.persistence import PersistedPrediction


class AssistantState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NO_PUBLIC_ANALYSIS = "NO_PUBLIC_ANALYSIS"
    EXTERNAL_ACTIVATION_REQUIRED = "EXTERNAL_ACTIVATION_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


class CouponRisk(StrEnum):
    SAFE = "SAFE"
    BALANCED = "BALANCED"
    BOLD = "BOLD"


class CouponState(StrEnum):
    READY = "READY"
    INSUFFICIENT_ELIGIBLE_POOL = "INSUFFICIENT_ELIGIBLE_POOL"
    EMPTY = "EMPTY"


@dataclass(frozen=True)
class PublicAnalysisContext:
    match_id: int
    market: str
    selection: str
    publication_state: str
    model_probability: Decimal
    bet_score: Decimal | None
    edge: Decimal | None
    final_check: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class AssistantAnswer:
    state: AssistantState
    answer: str | None
    context: PublicAnalysisContext | None


@dataclass(frozen=True)
class CouponResult:
    state: CouponState
    risk: CouponRisk
    requested_count: int
    selections: tuple[PublicAnalysisContext, ...]


class AssistantAdapter(Protocol):
    def explain(self, context: PublicAnalysisContext, question: str | None) -> str: ...


class ExternalAssistantAdapter:
    """Fail-closed production boundary until an authorized adapter exists."""

    def explain(self, context: PublicAnalysisContext, question: str | None) -> str:
        del context, question
        raise RuntimeError("AI execution requires external activation")


class DeterministicTestAssistant:
    """Contract-test adapter that cannot create or alter predictions."""

    def explain(self, context: PublicAnalysisContext, question: str | None) -> str:
        del question
        return (
            f"Published {context.market} analysis selects {context.selection}. "
            "No independent prediction was created."
        )


def public_context(record: PersistedPrediction) -> PublicAnalysisContext:
    if not record.public_candidate:
        raise ValueError("assistant context requires active publication-eligible evidence")
    limitations = tuple(sorted(set(record.blockers)))
    return PublicAnalysisContext(
        match_id=record.match_id,
        market=record.market,
        selection=record.selection,
        publication_state=record.policy_decision,
        model_probability=record.model_probability,
        bet_score=record.bet_score,
        edge=record.edge if record.market_observed_at is not None else None,
        final_check="FINAL_CHECK_UNAVAILABLE",
        limitations=limitations,
    )


def explain_public_prediction(
    record: PersistedPrediction | None,
    adapter: AssistantAdapter,
    *,
    question: str | None = None,
) -> AssistantAnswer:
    if record is None:
        return AssistantAnswer(AssistantState.NO_PUBLIC_ANALYSIS, None, None)
    context = public_context(record)
    try:
        answer = adapter.explain(context, question)
    except RuntimeError:
        return AssistantAnswer(AssistantState.EXTERNAL_ACTIVATION_REQUIRED, None, context)
    return AssistantAnswer(AssistantState.AVAILABLE, answer, context)


def unsupported_prediction_request() -> AssistantAnswer:
    return AssistantAnswer(AssistantState.UNSUPPORTED, None, None)


def build_coupon(
    records: tuple[PersistedPrediction, ...],
    *,
    risk: CouponRisk,
    requested_count: int,
) -> CouponResult:
    if not 1 <= requested_count <= 4:
        raise ValueError("coupon selection count must be between one and four")
    eligible = [record for record in records if record.public_candidate]
    ordered = sorted(eligible, key=lambda item: _coupon_key(item, risk))
    unique: list[PersistedPrediction] = []
    seen_matches: set[int] = set()
    for record in ordered:
        if record.match_id in seen_matches:
            continue
        unique.append(record)
        seen_matches.add(record.match_id)
        if len(unique) == requested_count:
            break
    contexts = tuple(public_context(item) for item in unique)
    if not contexts:
        state = CouponState.EMPTY
    elif len(contexts) < requested_count:
        state = CouponState.INSUFFICIENT_ELIGIBLE_POOL
    else:
        state = CouponState.READY
    return CouponResult(state, risk, requested_count, contexts)


def _coupon_key(record: PersistedPrediction, risk: CouponRisk) -> tuple[object, ...]:
    score = record.bet_score if record.bet_score is not None else Decimal("-1")
    if risk is CouponRisk.SAFE:
        preference = (-score, -record.model_probability, -record.edge)
    elif risk is CouponRisk.BOLD:
        preference = (-record.edge, -score, -record.model_probability)
    else:
        preference = (-score, -record.edge, -record.model_probability)
    return (*preference, record.match_id, record.market, record.selection)
