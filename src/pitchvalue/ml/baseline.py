"""Train-fold-only class-prior comparator for TASK 16."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from pitchvalue.ml.contracts import TrainingRow
from pitchvalue.ml.model import ML_CLASS_ORDER, MLClassProbability


def train_prior_probabilities(rows: tuple[TrainingRow, ...]) -> tuple[MLClassProbability, ...]:
    if not rows:
        raise ValueError("TRAIN_PRIOR requires training rows")
    counts = Counter(row.target_value for row in rows)
    total = Decimal(len(rows))
    return tuple(
        MLClassProbability(selection, Decimal(counts[selection]) / total)
        for selection in ML_CLASS_ORDER
    )
