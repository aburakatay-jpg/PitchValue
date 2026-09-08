"""Immutable configuration for deterministic temporal evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any


class EvaluationValidationError(ValueError):
    """Raised when an evaluation contract or configuration is invalid."""


class SplitStrategy(StrEnum):
    EXPANDING = "EXPANDING"
    ROLLING = "ROLLING"


class BoundaryPolicy(StrEnum):
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class WalkForwardConfig:
    """Engineering defaults for chronological walk-forward folds.

    ``training_window`` is the initial span for expanding evaluation and the
    bounded span for rolling evaluation. All windows use half-open intervals.
    """

    strategy: SplitStrategy = SplitStrategy.EXPANDING
    training_window: timedelta = timedelta(days=28)
    test_window: timedelta = timedelta(days=7)
    step_size: timedelta = timedelta(days=7)
    embargo: timedelta = timedelta(0)
    minimum_training_samples: int = 1
    minimum_test_samples: int = 1
    boundary_policy: BoundaryPolicy = BoundaryPolicy.HALF_OPEN

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, SplitStrategy):
            raise EvaluationValidationError("strategy must use SplitStrategy")
        if not isinstance(self.boundary_policy, BoundaryPolicy):
            raise EvaluationValidationError("boundary_policy must use BoundaryPolicy")
        for name in ("training_window", "test_window", "step_size"):
            value = getattr(self, name)
            if not isinstance(value, timedelta) or value <= timedelta(0):
                raise EvaluationValidationError(f"{name} must be a positive timedelta")
        if not isinstance(self.embargo, timedelta) or self.embargo < timedelta(0):
            raise EvaluationValidationError("embargo must be a non-negative timedelta")
        for name in ("minimum_training_samples", "minimum_test_samples"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise EvaluationValidationError(f"{name} must be at least 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "training_window_seconds": self.training_window.total_seconds(),
            "test_window_seconds": self.test_window.total_seconds(),
            "step_size_seconds": self.step_size.total_seconds(),
            "embargo_seconds": self.embargo.total_seconds(),
            "minimum_training_samples": self.minimum_training_samples,
            "minimum_test_samples": self.minimum_test_samples,
            "boundary_policy": self.boundary_policy.value,
        }
