"""Pure adapters from independent model outputs into shared signals."""

from __future__ import annotations

from decimal import Decimal

from pitchvalue.models.elo.contracts import EloSnapshot
from pitchvalue.models.form.contracts import FormModelAnalysis, FormModelStatus
from pitchvalue.models.poisson.contracts import PoissonAnalysis, PoissonModelStatus
from pitchvalue.models.signals.config import (
    DEFAULT_SIGNAL_AGREEMENT_CONFIG,
    ModelFamily,
    SignalAgreementConfig,
    SignalValidationError,
)
from pitchvalue.models.signals.contracts import (
    DirectionalPreference,
    ModelSignal,
    SignalDiagnostic,
    SignalStatus,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


def _unavailable_signal(
    family: ModelFamily,
    match_id: str,
    market: MarketFamily,
    status: SignalStatus,
    reason: str,
) -> ModelSignal:
    return ModelSignal(
        model_family=family,
        model_name=f"{family.value.lower()}-v1",
        match_id=match_id,
        market=market,
        selection=None,
        direction=None,
        signal_status=status,
        normalized_strength=None,
        diagnostics=(SignalDiagnostic("reason", reason),),
    )


def adapt_poisson_signal(
    analysis: PoissonAnalysis,
    *,
    market: MarketFamily = MarketFamily.MATCH_RESULT,
    line: Decimal | None = None,
    config: SignalAgreementConfig = DEFAULT_SIGNAL_AGREEMENT_CONFIG,
) -> ModelSignal:
    if analysis.status is PoissonModelStatus.INPUT_INSUFFICIENT:
        return _unavailable_signal(
            ModelFamily.POISSON,
            analysis.match_id,
            market,
            SignalStatus.INPUT_INSUFFICIENT,
            "POISSON_INPUT_INSUFFICIENT",
        )
    if analysis.status is not PoissonModelStatus.READY:
        return _unavailable_signal(
            ModelFamily.POISSON,
            analysis.match_id,
            market,
            SignalStatus.INVALID,
            "POISSON_INVALID",
        )
    if analysis.markets is None or analysis.diagnostics is None:
        return _unavailable_signal(
            ModelFamily.POISSON,
            analysis.match_id,
            market,
            SignalStatus.INVALID,
            "POISSON_OUTPUT_INCOMPLETE",
        )
    if market is MarketFamily.MATCH_RESULT:
        residual = Decimal(1) - analysis.diagnostics.one_x_two_represented_mass
        if not Decimal(0) <= residual <= Decimal(1):
            return _unavailable_signal(
                ModelFamily.POISSON,
                analysis.match_id,
                market,
                SignalStatus.INVALID,
                "POISSON_RESIDUAL_INVALID",
            )
        if residual > config.poisson_residual_mass_tolerance:
            return _unavailable_signal(
                ModelFamily.POISSON,
                analysis.match_id,
                market,
                SignalStatus.ANALYSIS_UNAVAILABLE,
                "POISSON_RESIDUAL_EXCEEDS_TOLERANCE",
            )
    else:
        residual = analysis.diagnostics.matrix_residual_mass
    candidates = tuple(
        value for value in analysis.markets.values if value.market is market and value.line == line
    )
    if not candidates:
        return _unavailable_signal(
            ModelFamily.POISSON,
            analysis.match_id,
            market,
            SignalStatus.UNSUPPORTED_MARKET,
            "POISSON_MARKET_UNSUPPORTED",
        )
    ranked = sorted(candidates, key=lambda value: value.probability, reverse=True)
    if len(ranked) > 1 and (
        ranked[0].probability - ranked[1].probability <= config.poisson_ambiguity_tolerance
    ):
        return ModelSignal(
            model_family=ModelFamily.POISSON,
            model_name="poisson-v1",
            match_id=analysis.match_id,
            market=market,
            selection=None,
            direction=None,
            signal_status=SignalStatus.AMBIGUOUS,
            normalized_strength=None,
            diagnostics=(
                SignalDiagnostic("top_probability", ranked[0].probability),
                SignalDiagnostic("second_probability", ranked[1].probability),
                SignalDiagnostic("residual_mass", residual),
            ),
        )
    selected = ranked[0]
    direction = (
        DirectionalPreference.HOME
        if selected.selection is Selection.HOME
        else DirectionalPreference.AWAY
        if selected.selection is Selection.AWAY
        else None
    )
    return ModelSignal(
        model_family=ModelFamily.POISSON,
        model_name="poisson-v1",
        match_id=analysis.match_id,
        market=market,
        selection=selected.selection,
        direction=direction,
        signal_status=SignalStatus.READY,
        normalized_strength=selected.probability,
        line=selected.line,
        probability=selected.probability,
        raw_value=selected.probability,
        diagnostics=(
            SignalDiagnostic("residual_mass", residual),
            SignalDiagnostic("probability_renormalized", False),
        ),
    )


def adapt_elo_signal(
    snapshot: EloSnapshot | None,
    *,
    match_id: str | None = None,
    market: MarketFamily = MarketFamily.MATCH_RESULT,
    config: SignalAgreementConfig = DEFAULT_SIGNAL_AGREEMENT_CONFIG,
) -> ModelSignal:
    if snapshot is not None and match_id is not None and snapshot.target_match_id != match_id:
        raise SignalValidationError("explicit match_id does not match Elo snapshot")
    resolved_match_id = snapshot.target_match_id if snapshot is not None else match_id
    if not isinstance(resolved_match_id, str) or not resolved_match_id.strip():
        raise SignalValidationError("match_id is required when Elo snapshot is unavailable")
    if market is not MarketFamily.MATCH_RESULT:
        return _unavailable_signal(
            ModelFamily.ELO,
            resolved_match_id,
            market,
            SignalStatus.UNSUPPORTED_MARKET,
            "ELO_MARKET_UNSUPPORTED",
        )
    if snapshot is None:
        return _unavailable_signal(
            ModelFamily.ELO,
            resolved_match_id,
            market,
            SignalStatus.ANALYSIS_UNAVAILABLE,
            "ELO_SNAPSHOT_UNAVAILABLE",
        )
    expected = snapshot.expected_home_score
    away_expected = snapshot.expected_away_score
    if (
        not isinstance(expected, Decimal)
        or not expected.is_finite()
        or not isinstance(away_expected, Decimal)
        or not away_expected.is_finite()
        or not Decimal(0) <= expected <= Decimal(1)
        or expected + away_expected != Decimal(1)
    ):
        return _unavailable_signal(
            ModelFamily.ELO,
            resolved_match_id,
            market,
            SignalStatus.INVALID,
            "ELO_EXPECTATION_INVALID",
        )
    if expected >= config.elo_home_threshold:
        direction = DirectionalPreference.HOME
        selection = Selection.HOME
    elif expected <= config.elo_away_threshold:
        direction = DirectionalPreference.AWAY
        selection = Selection.AWAY
    else:
        direction = DirectionalPreference.NEUTRAL
        selection = None
    strength = abs(expected - Decimal("0.5")) * Decimal(2)
    return ModelSignal(
        model_family=ModelFamily.ELO,
        model_name="elo-v1",
        match_id=resolved_match_id,
        market=market,
        selection=selection,
        direction=direction,
        signal_status=SignalStatus.READY,
        normalized_strength=strength,
        probability=None,
        raw_value=expected,
        diagnostics=(
            SignalDiagnostic(
                "home_adjusted_rating_difference",
                snapshot.home_adjusted_rating_difference,
            ),
            SignalDiagnostic("expected_home_score", expected),
            SignalDiagnostic("expected_score_is_probability", False),
        ),
    )


def adapt_form_signal(
    analysis: FormModelAnalysis | None,
    *,
    match_id: str | None = None,
    market: MarketFamily = MarketFamily.MATCH_RESULT,
    config: SignalAgreementConfig = DEFAULT_SIGNAL_AGREEMENT_CONFIG,
) -> ModelSignal:
    if analysis is not None and match_id is not None and analysis.match_id != match_id:
        raise SignalValidationError("explicit match_id does not match Form analysis")
    resolved_match_id = analysis.match_id if analysis is not None else match_id
    if not isinstance(resolved_match_id, str) or not resolved_match_id.strip():
        raise SignalValidationError("match_id is required when Form analysis is unavailable")
    if market is not MarketFamily.MATCH_RESULT:
        return _unavailable_signal(
            ModelFamily.FORM,
            resolved_match_id,
            market,
            SignalStatus.UNSUPPORTED_MARKET,
            "FORM_MARKET_UNSUPPORTED",
        )
    if analysis is None:
        return _unavailable_signal(
            ModelFamily.FORM,
            resolved_match_id,
            market,
            SignalStatus.ANALYSIS_UNAVAILABLE,
            "FORM_ANALYSIS_UNAVAILABLE",
        )
    if analysis.status is FormModelStatus.INPUT_INSUFFICIENT:
        return _unavailable_signal(
            ModelFamily.FORM,
            resolved_match_id,
            market,
            SignalStatus.INPUT_INSUFFICIENT,
            "FORM_INPUT_INSUFFICIENT",
        )
    if analysis.status is not FormModelStatus.READY:
        return _unavailable_signal(
            ModelFamily.FORM,
            resolved_match_id,
            market,
            SignalStatus.INVALID,
            "FORM_ANALYSIS_INVALID",
        )
    relative = analysis.home_relative_form_signal
    if (
        not isinstance(relative, Decimal)
        or not relative.is_finite()
        or not Decimal(-1) <= relative <= Decimal(1)
    ):
        return _unavailable_signal(
            ModelFamily.FORM,
            resolved_match_id,
            market,
            SignalStatus.INVALID,
            "FORM_RELATIVE_SIGNAL_INVALID",
        )
    if relative >= config.form_home_threshold:
        direction = DirectionalPreference.HOME
        selection = Selection.HOME
    elif relative <= config.form_away_threshold:
        direction = DirectionalPreference.AWAY
        selection = Selection.AWAY
    else:
        direction = DirectionalPreference.NEUTRAL
        selection = None
    return ModelSignal(
        model_family=ModelFamily.FORM,
        model_name="form-v1",
        match_id=resolved_match_id,
        market=market,
        selection=selection,
        direction=direction,
        signal_status=SignalStatus.READY,
        normalized_strength=abs(relative),
        probability=None,
        raw_value=relative,
        diagnostics=(
            SignalDiagnostic("relative_form_signal", relative),
            SignalDiagnostic("relative_signal_is_probability", False),
        ),
    )
