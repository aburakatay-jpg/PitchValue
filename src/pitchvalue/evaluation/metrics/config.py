"""Immutable engineering configuration for probability-quality metrics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class MetricValidationError(ValueError):
    """Raised when metric configuration or an input contract is invalid."""


DEFAULT_BUCKET_EDGES = tuple(Decimal(index) / Decimal(10) for index in range(11))


def _finite_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise MetricValidationError(f"{name} must be a finite Decimal")
    return value


@dataclass(frozen=True)
class MetricConfig:
    """Numerical and evidence thresholds; defaults are not empirically optimized."""

    log_loss_epsilon: Decimal = Decimal("1e-15")
    probability_sum_tolerance: Decimal = Decimal("1e-12")
    binary_threshold: Decimal = Decimal("0.5")
    bucket_edges: tuple[Decimal, ...] = DEFAULT_BUCKET_EDGES
    minimum_total_samples: int = 1
    minimum_bucket_samples: int = 1

    def __post_init__(self) -> None:
        epsilon = _finite_decimal(self.log_loss_epsilon, "log_loss_epsilon")
        tolerance = _finite_decimal(self.probability_sum_tolerance, "probability_sum_tolerance")
        threshold = _finite_decimal(self.binary_threshold, "binary_threshold")
        if not Decimal(0) < epsilon < Decimal("0.5"):
            raise MetricValidationError("log_loss_epsilon must be between 0 and 0.5")
        if tolerance <= 0:
            raise MetricValidationError("probability_sum_tolerance must be positive")
        if not Decimal(0) <= threshold <= Decimal(1):
            raise MetricValidationError("binary_threshold must be between 0 and 1")
        if len(self.bucket_edges) < 2:
            raise MetricValidationError("bucket_edges must contain at least two boundaries")
        if any(not isinstance(edge, Decimal) or not edge.is_finite() for edge in self.bucket_edges):
            raise MetricValidationError("bucket_edges must contain finite Decimals")
        if self.bucket_edges[0] != Decimal(0) or self.bucket_edges[-1] != Decimal(1):
            raise MetricValidationError("bucket_edges must start at 0 and end at 1")
        if any(
            left >= right
            for left, right in zip(self.bucket_edges, self.bucket_edges[1:], strict=False)
        ):
            raise MetricValidationError("bucket_edges must be strictly increasing")
        for name in ("minimum_total_samples", "minimum_bucket_samples"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise MetricValidationError(f"{name} must be at least 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "log_loss_epsilon": str(self.log_loss_epsilon),
            "probability_sum_tolerance": str(self.probability_sum_tolerance),
            "binary_threshold": str(self.binary_threshold),
            "bucket_edges": [str(edge) for edge in self.bucket_edges],
            "minimum_total_samples": self.minimum_total_samples,
            "minimum_bucket_samples": self.minimum_bucket_samples,
        }
