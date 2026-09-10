# TASK 16 baseline ML model

TASK 16 implements one deliberately simple production-candidate baseline: deterministic
multinomial logistic regression for `MATCH_RESULT`, with the explicit class order `HOME`, `DRAW`,
`AWAY`. The TASK 16 default model uses football-performance features only.
Historical bookmaker odds are excluded from the default ML feature profile.

## Inputs and target

The real-data adapter reads completed canonical domestic matches and creates TASK 15 training rows.
Each prediction cutoff is 24 hours before kickoff. TASK 06 features and the TASK 07 pre-match Elo
state are calculated only from matches strictly before that cutoff. The semantic target remains
separate from the feature vector and is derived from the completed target match after feature
construction.

The feature schema contains Elo strength state, recent and extended form, venue form, scoring and
conceding history, clean-sheet and failed-to-score rates, historical BTTS/totals rates, rest and
fixture density, and league baselines. Team identifiers are not model features. Odds, implied
probabilities, no-vig values, edge, scores, results, and post-match statistics are structurally
excluded.

## Preprocessing and missing values

Preprocessing is fitted separately inside every training fold. Available numeric values receive a
training-fold mean and standard deviation. Missing values use that training-fold mean only for the
numeric model boundary and receive a separate missing indicator. Missing is never interpreted as
zero, and test-fold values cannot influence means, scales, or model coefficients. No categorical
encoding or team-ID memorization is used.

## Training and evaluation

The model is a standard-library softmax/multinomial logistic regression with fixed configuration,
fixed class order, deterministic full-batch updates, L2 regularization, and explicit model version
`multinomial_logistic_v1`. The seed is recorded even though the current optimizer uses no random
operation.

TASK 13 expanding walk-forward folds are the only production-style evaluation path.
Random train/test splitting is not used for production-style evaluation.
Every fitted fold has training
prediction cutoffs strictly before its test window, and insufficient folds are reported rather than
hidden.

TASK 14 supplies multiclass Log Loss, raw summed multiclass Brier Score, supporting accuracy, and
class-wise bucketed calibration diagnostics. Metrics aggregate only out-of-sample fold predictions.
The comparison baseline is `TRAIN_PRIOR`, calculated solely from each fold's training class
frequencies.

TASK 16 probabilities are uncalibrated model outputs. Reliability buckets and ECE-like values are
diagnostics only; no calibrator is fitted. TASK 17 owns calibration fitting. TASK 18 owns any future
ensemble decision.
A working ML model is not evidence that ML should receive non-zero ensemble weight.

## Odds experiment and limitations

The odds-inclusive profile is not evaluated because TASK 12 historical observations have role-only
timing and no exact quote timestamps. They cannot be assumed available at arbitrary historical
prediction cutoffs. The football-only baseline does not query or modify `odds_snapshots`.

This first historical run measures out-of-sample probability behavior, not profitability or launch
readiness. It performs no calibration fitting, ensemble, edge, EV, ROI, Kelly, Bet Score,
publication decision, settlement, schema migration, or model-artifact persistence.
