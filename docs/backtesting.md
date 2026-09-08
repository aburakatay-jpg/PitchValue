# Backtesting foundation

PitchValue uses walk-forward evaluation as the canonical production validation strategy for
temporal football data. Random train/test splitting is intentionally absent: it can train a model
with information that occurred after the matches it is supposedly predicting.

## Temporal contract

Every target has a timezone-aware `prediction_as_of` and `kickoff`, with
`prediction_as_of < kickoff`. Observations preserve their match kickoff and the time at which they
became available. A prediction-time feature is legal only when `available_at <= prediction_as_of`.
This matters even when its underlying events are old: a season aggregate recalculated after future
matches is not valid for an earlier prediction merely because some source rows predate it.

The target match is never legal training material for itself. Future observations, same-kickoff
observations, target results, and outcomes claimed before match resolution are reported as typed
leakage diagnostics. Timestamps are never shifted or repaired automatically.

Odds have the same availability rule. Closing odds observed after `prediction_as_of` must not be
used as prediction-time features. Feature-time odds, later evaluation/reference odds, and closing
reference odds remain distinct semantics; a later price can be retained for a future post-hoc
benchmark without being admitted to prediction state.

## Walk-forward windows

Both strategies use explicit half-open intervals: `[train_start, train_end)` and
`[test_start, test_end)`. An optional non-negative embargo moves `test_start` after `train_end`.

- Expanding: the training start remains fixed while its end advances by the configured step.
- Rolling: both training boundaries advance while the configured training span stays bounded.

The engineering defaults are a 28-day initial/bounded training span, a 7-day test span, a 7-day
step, and no embargo. They are configuration defaults, not optimized parameters. Input is sorted by
kickoff and stable observation ID. Duplicate IDs are rejected, and input ordering cannot alter the
canonical folds.

## Audit and sample sufficiency

Contracts preserve competition, season, market, selection, line, model/feature versions, fold, and
source provenance. Fold and run summaries expose counts and typed readiness/insufficiency states;
they contain no predictive or betting metrics. A high return observed on a tiny evaluation sample
is not sufficient launch evidence.

This task is a synthetic-only framework correctness foundation. It does not execute a real
historical backtest, train a model, normalize odds, calculate Brier score, Log Loss, calibration,
edge, EV, ROI, or publication decisions. Synthetic framework correctness does not prove model
performance. Real data and later metric/calibration tasks are required for evidence.
