"""Shared independent-model signals and explicit-support agreement."""

from pitchvalue.models.signals.adapters import (
    adapt_elo_signal,
    adapt_form_signal,
    adapt_poisson_signal,
)
from pitchvalue.models.signals.agreement import (
    evaluate_agreement,
    evaluate_match_result_agreement,
)
from pitchvalue.models.signals.config import (
    DEFAULT_SIGNAL_AGREEMENT_CONFIG,
    ModelFamily,
    SignalAgreementConfig,
)
from pitchvalue.models.signals.contracts import AgreementResult, ModelSignal

__all__ = [
    "DEFAULT_SIGNAL_AGREEMENT_CONFIG",
    "AgreementResult",
    "ModelFamily",
    "ModelSignal",
    "SignalAgreementConfig",
    "adapt_elo_signal",
    "adapt_form_signal",
    "adapt_poisson_signal",
    "evaluate_agreement",
    "evaluate_match_result_agreement",
]
