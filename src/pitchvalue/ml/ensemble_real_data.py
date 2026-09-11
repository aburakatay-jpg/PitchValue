"""Read-only TASK 06–09 evidence adapter for real TASK 18 evaluation."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Connection

from pitchvalue.features import compute_match_features
from pitchvalue.features.contracts import TargetFixture
from pitchvalue.ml.config import MLDatasetValidationError
from pitchvalue.ml.contracts import MLDataset
from pitchvalue.ml.ensemble import ProbabilityModelPrediction
from pitchvalue.ml.ensemble_evaluation import EnsembleModelEvidence
from pitchvalue.ml.model import ML_CLASS_ORDER, MLClassProbability
from pitchvalue.ml.real_data import _load_history
from pitchvalue.models.elo import target_elo_snapshot
from pitchvalue.models.form import analyze_form_signal
from pitchvalue.models.poisson import analyze_poisson, input_from_match_features
from pitchvalue.models.poisson.config import PoissonValidationError
from pitchvalue.models.poisson.contracts import PoissonModelStatus
from pitchvalue.models.signals import adapt_elo_signal, adapt_form_signal
from pitchvalue.prediction.contracts import MarketFamily


def load_real_ensemble_evidence(
    connection: Connection, dataset: MLDataset
) -> tuple[EnsembleModelEvidence, ...]:
    """Recompute only pre-match model evidence; never query odds or mutate the database."""
    history, season_order, _, _ = _load_history(connection)
    matches = {match.match_id: match for match in history}
    result: list[EnsembleModelEvidence] = []
    for row in dataset.rows:
        match = matches[row.match_id]
        target = TargetFixture(
            match.match_id,
            match.competition_id,
            match.season_id,
            match.kickoff,
            match.home_team_id,
            match.away_team_id,
            row.prediction_as_of,
        )
        features = compute_match_features(target, history)
        poisson_prediction = None
        poisson_reasons: tuple[str, ...] = ()
        try:
            poisson = analyze_poisson(input_from_match_features(features))
        except (PoissonValidationError, ArithmeticError) as exc:
            poisson = None
            poisson_reasons = (f"POISSON_INVALID_INPUT:{exc}",)
        if poisson is not None and (
            poisson.status is PoissonModelStatus.READY
            and poisson.markets is not None
            and poisson.diagnostics is not None
        ):
            poisson_prediction = ProbabilityModelPrediction(
                row.row_id,
                row.match_id,
                row.prediction_as_of,
                "POISSON",
                "poisson_v1",
                ML_CLASS_ORDER,
                tuple(
                    MLClassProbability(
                        selection,
                        poisson.markets.get(MarketFamily.MATCH_RESULT, selection),
                    )
                    for selection in ML_CLASS_ORDER
                ),
                Decimal(1) - poisson.diagnostics.one_x_two_represented_mass,
            )
            try:
                poisson_prediction.validate(Decimal("0.001"))
            except MLDatasetValidationError as exc:
                poisson_prediction = None
                poisson_reasons = (f"POISSON_INVALID_PROBABILITY:{exc}",)
        elif poisson is not None:
            poisson_reasons = tuple(
                f"POISSON_{poisson.status.value}:{reason}" for reason in poisson.reasons
            ) or (f"POISSON_{poisson.status.value}",)
        elo = target_elo_snapshot(
            target,
            history,
            season_order=season_order[match.competition_id],
        )
        form = analyze_form_signal(features)
        result.append(
            EnsembleModelEvidence(
                row.row_id,
                row.match_id,
                row.prediction_as_of,
                poisson_prediction,
                adapt_elo_signal(elo),
                adapt_form_signal(form),
                poisson_reasons,
            )
        )
    return tuple(result)
