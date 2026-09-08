# ML dataset foundation

TASK 15 defines a pure, immutable transformation from synthetic pre-match feature records and resolved outcomes into supervised-learning rows. It builds data contracts; it does not train a model, encode labels for a library, split data, calculate metrics, or make predictions.

## Row and time semantics

Every row preserves match, competition, season, kickoff, `prediction_as_of`, feature-schema version, feature profile, target definition, target value, ordered features, and provenance. `prediction_as_of` must be timezone-aware and strictly before kickoff.

Every feature must have been available at or before `prediction_as_of`. A later `available_at` makes the feature illegal even when its underlying source matches are old. This prevents later-recalculated form or season aggregates from being reused for earlier predictions. Source matches must occur strictly before the cutoff; equal-time sources are not historical information. Target match IDs, target-result flags, and target-goal flags in feature provenance are explicit leakage failures.

The target value must never appear inside the feature vector. Resolved score data is used only by target derivation, after the prediction-time feature boundary has been validated.

## Feature schema and provenance

The immutable schema declares one version and an explicit required/optional feature order. Dataset rows cannot silently add unknown features, resolve duplicate names, or mix feature versions. Input order never defines the vector order.

Each feature carries its name, typed scalar or explicit missing value, `available_at`, schema version, calculation version, source module, source-data version, calculation ID, and canonically ordered source-match references. This is sufficient to audit why a value was legal at a particular cutoff without creating a lineage database.

Missing values are not zero and are not silently imputed. They are not `0.5`, a league average, or a mean. `PRESERVE_MISSING` retains an explicit `None` and reason; `REJECT_ROW` rejects a missing required feature. Optional missing values remain explicit.

## Targets

Targets keep semantic labels rather than permanent numeric encodings. Supported V1 definitions are Match Result, BTTS, total goals 1.5/2.5, home team totals 0.5/1.5, away team totals 0.5/1.5, and explicit binary Double Chance selections. Only ordinary `FINISHED` outcomes with valid non-negative scores produce labels.

Double Chance selections overlap and must not be encoded as one exclusive three-class target. `1X`, `X2`, and `12` are each separate true/false target definitions.

## Odds feature policy

The default ML baseline excludes bookmaker odds features. `FOOTBALL_PERFORMANCE_ONLY` is a deliberate independence boundary, not an accidental omission. Raw implied probability and no-vig probability are not silently inserted.

Odds-inclusive ML must be evaluated as a separate out-of-sample experiment through `ODDS_INCLUSIVE_EXPERIMENT`, an explicitly declared schema, and explicit market-feature semantics. The same time rule applies: a closing price observed at 19:45 cannot enter a prediction made at 10:00, even if kickoff is at 20:00.

## Dataset identity and determinism

Row identity includes match ID, semantic target (including line or Double Chance selection), `prediction_as_of`, and schema version. This permits multiple markets, lines, and prediction snapshots for one match while rejecting exact duplicates. Rows sort canonically by kickoff, match, target, and cutoff. Feature and provenance ordering is stable; Decimal values and aware timestamps serialize deterministically. Caller objects are never mutated and no random or clock-generated ID is used.

The dataset reports input, ready, explicit-missing, rejected, leakage, schema, and target counts. `EMPTY`, `PARTIAL`, and `INVALID` do not masquerade as usable training evidence.

## Boundaries and current status

TASK 13 remains responsible for expanding/rolling walk-forward splits. TASK 14 remains responsible for probability metrics. TASK 15 implements no pandas/NumPy requirement, ML library, training, scaling, encoding, feature selection, balancing, calibration, ensemble, odds normalization, edge, ROI, persistence, or API.

Validation is synthetic only. Correct leakage-safe dataset construction does not prove feature quality, model quality, calibration, profitability, or launch readiness. Real materialization and training remain blocked behind the historical-data integrity gate.
