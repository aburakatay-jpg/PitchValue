"""Deterministic explicit-support agreement calculations without blending."""

from __future__ import annotations

from decimal import Decimal

from pitchvalue.models.signals.config import (
    DEFAULT_SIGNAL_AGREEMENT_CONFIG,
    ModelFamily,
    SignalAgreementConfig,
    SignalValidationError,
)
from pitchvalue.models.signals.contracts import (
    AgreementDiagnostics,
    AgreementResult,
    DirectionalPreference,
    ModelSignal,
    SignalDiagnostic,
    SignalStatus,
    validate_market_position,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


def evaluate_agreement(
    signals: tuple[ModelSignal, ...] | list[ModelSignal],
    *,
    match_id: str,
    market: MarketFamily,
    candidate_selection: Selection,
    candidate_line: Decimal | None = None,
    config: SignalAgreementConfig = DEFAULT_SIGNAL_AGREEMENT_CONFIG,
) -> AgreementResult:
    if not isinstance(match_id, str) or not match_id.strip():
        raise SignalValidationError("match_id is required")
    if not isinstance(market, MarketFamily) or not isinstance(candidate_selection, Selection):
        raise SignalValidationError("market and selection must use canonical contracts")
    validate_market_position(market, candidate_selection, candidate_line)
    by_family: dict[ModelFamily, ModelSignal] = {}
    for signal in signals:
        if not isinstance(signal, ModelSignal):
            raise SignalValidationError("signals must contain ModelSignal values")
        if signal.model_family in by_family:
            raise SignalValidationError("one signal per model family is allowed")
        if signal.match_id != match_id or signal.market is not market:
            raise SignalValidationError("signal match and market must match agreement request")
        if signal.model_family not in config.configured_model_families:
            raise SignalValidationError("signal model family is not configured")
        by_family[signal.model_family] = signal

    agreeing: list[ModelFamily] = []
    conflicting: list[ModelFamily] = []
    neutral: list[ModelFamily] = []
    unavailable: list[ModelFamily] = []
    statuses: list[SignalDiagnostic] = []
    usable = 0
    for family in config.configured_model_families:
        family_signal = by_family.get(family)
        if family_signal is None:
            unavailable.append(family)
            statuses.append(SignalDiagnostic(family.value, "NOT_PROVIDED"))
            continue
        statuses.append(SignalDiagnostic(family.value, family_signal.signal_status.value))
        if family_signal.signal_status is not SignalStatus.READY:
            unavailable.append(family)
            continue
        if family_signal.line != candidate_line:
            unavailable.append(family)
            statuses[-1] = SignalDiagnostic(family.value, "LINE_MISMATCH")
            continue
        usable += 1
        if family_signal.direction is DirectionalPreference.NEUTRAL:
            neutral.append(family)
        elif family_signal.selection is candidate_selection:
            agreeing.append(family)
        else:
            conflicting.append(family)

    supporting = len(agreeing)
    configured_count = len(config.configured_model_families)
    usable_ratio = Decimal(supporting) / Decimal(usable) if usable else None
    configured_ratio = Decimal(supporting) / Decimal(configured_count)
    return AgreementResult(
        match_id=match_id,
        market=market,
        candidate_selection=candidate_selection,
        candidate_line=candidate_line,
        supporting_model_count=supporting,
        usable_model_count=usable,
        configured_model_count=configured_count,
        usable_agreement_ratio=usable_ratio,
        configured_agreement_ratio=configured_ratio,
        agreeing_models=tuple(agreeing),
        conflicting_models=tuple(conflicting),
        neutral_models=tuple(neutral),
        unavailable_models=tuple(unavailable),
        sufficient_usable_models=usable >= config.minimum_usable_models,
        meets_configured_agreement_ratio=(configured_ratio >= config.required_agreement_ratio),
        diagnostics=AgreementDiagnostics(
            required_agreement_ratio=config.required_agreement_ratio,
            minimum_usable_models=config.minimum_usable_models,
            signal_statuses=tuple(statuses),
        ),
    )


def evaluate_match_result_agreement(
    signals: tuple[ModelSignal, ...] | list[ModelSignal],
    *,
    match_id: str,
    config: SignalAgreementConfig = DEFAULT_SIGNAL_AGREEMENT_CONFIG,
) -> tuple[AgreementResult, ...]:
    return tuple(
        evaluate_agreement(
            signals,
            match_id=match_id,
            market=MarketFamily.MATCH_RESULT,
            candidate_selection=selection,
            config=config,
        )
        for selection in (Selection.HOME, Selection.DRAW, Selection.AWAY)
    )
