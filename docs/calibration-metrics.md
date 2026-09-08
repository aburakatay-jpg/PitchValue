# Calibration metrics foundation

Calibration metrics measure probability quality; they do not calibrate the model. This package
accepts explicit binary or multiclass probability records and produces deterministic diagnostics
that can later consume TASK 13 walk-forward results.

## Probability contracts

Binary probabilities must be finite Decimals in `[0, 1]`, with an explicit `0` or `1` outcome.
Multiclass records identify every class explicitly, reject duplicate labels, and must sum to one
within configured tolerance. A probability vector that does not sum to one within tolerance must
not be silently renormalized for evaluation. This includes Poisson 1X2 output with material residual
matrix mass; callers must provide a valid evaluation vector or accept an invalid-probability result.

Raw Elo, Form, and generic signal strength values must not be treated as calibrated probabilities.
The contracts require declared probability semantics and provide no strength-to-probability adapter.
Missing and unavailable predictions remain explicit, are excluded rather than imputed, and retain
input/usable/excluded counts.

## Probability-quality metrics

Binary Brier Score is the mean of `(p - y)^2` and ranges from zero to one. Multiclass Brier uses the
raw summed convention `sum((p_k - y_k)^2)` per observation, averaged across observations; for a
single-label outcome its range is zero to two. Lower is better.

Binary Log Loss uses `-[y log(p) + (1-y) log(1-p)]`; multiclass Log Loss uses the negative log of the
observed class probability. A configurable Decimal epsilon clips only the temporary logarithm input
at the controlled `Decimal -> float -> math.log -> Decimal` numerical boundary. Source probabilities
are not changed. Accuracy is reported separately as supporting classification information. High
accuracy does not imply good calibration. Multiclass top-probability ties are ambiguous and excluded
from accuracy while Brier and Log Loss remain calculable.

## Calibration buckets and ECE-like diagnostic

Bucket edges are configurable, strictly increasing, and must start at zero and end at one. Buckets
are lower-inclusive and upper-exclusive, except the final bucket includes one. Thus every valid
probability belongs to exactly one bucket.

Each bucket exposes sample count, mean predicted probability, observed positive frequency, signed
gap (`mean predicted - observed frequency`), absolute gap, and sample status. The baseline ECE-like
diagnostic is `sum((n_b / N) * absolute_gap_b)` over non-empty buckets. It depends on bucket choice
and is not a universal calibration truth. Multiclass calibration is reported one-vs-rest for every
class, with class-level ECE and a visible macro mean.

Minimum total and per-bucket sample thresholds are provisional engineering diagnostics. Empty input
never becomes a perfect score, and a single computable observation may still be marked insufficient
evidence.

## Current boundary

The implementation is synthetic-tested only. It does not fit isotonic, Platt, temperature, or any
other calibrator; train models; normalize odds; calculate edge, EV, ROI, or publication decisions;
or persist/expose results through a database or API. Real temporal data is required before model
calibration quality can be assessed.
