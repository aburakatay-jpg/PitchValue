# Historical odds observation schema

TASK 12A extends the existing `odds_snapshots` table. It does not normalize or
populate historical odds. Historical and future live prices remain one canonical
price-observation entity, distinguished by their origin, source kind, temporal role,
quality state, and lineage.

## Source and bookmaker semantics

`observation_origin` distinguishes `historical_source` from `live_source`.
`observation_source_kind` distinguishes an actual `bookmaker` quote from a
`source_average` or `source_maximum`. Bookmaker observations require a nonblank
bookmaker; source aggregates require bookmaker to be null. Source averages and
source maxima are not pseudo-bookmakers, PitchValue consensus, or PitchValue best
available prices.

## Temporal semantics

The canonical timestamp column is `observed_at`. It is the actual source quote
timestamp when known. Import time, staging time, file modification time, and runtime
time are not bookmaker observation time.

`observation_role` is one of `opening`, `source_prematch`, `source_final`, `closing`,
`unknown_prematch`, or `live`. `timing_semantics` is `exact`, `role_only`, or
`unknown`. Exact timing requires `observed_at`; role-only and unknown timing may
leave it null. A source-final historical row without a precise quote timestamp can
therefore remain `source_final`/`role_only` without being mislabeled as closing.

## Quality and lineage

`quality_status` is `eligible`, `suspect`, `excluded`, or `invalid`.
`quality_reasons` stores stable machine-readable tokens as a `TEXT[]`. Timing
uncertainty is orthogonal to quality status.

Historical observations must reference `football_data_staging_rows` through a
restricting foreign key and identify the exact `source_field`. The existing staging
chain supplies import-batch, raw hash, raw payload, and source identity; those values
are not duplicated in `odds_snapshots`.

## Versioning and idempotency

Historical rows require nonblank `mapping_version`, `normalization_version`, and
`quality_policy_version`. A partial unique index over staging row, source field, and
the three versions provides database-backed idempotency while allowing a future
versioned reinterpretation.

The existing Decimal-compatible `decimal_odds > 1` constraint and nullable
Decimal-compatible market line are unchanged. No probability columns are stored.

## Scope boundary

TASK 12A adds schema semantics only. It does not extract B365 fields, normalize or
persist historical prices, implement source-quality policies, calculate implied or
no-vig probabilities, change temporal evaluation, add ML features, train ML,
calibrate models, blend models, calculate edge or ROI, or publish predictions.
