# Historical Odds Normalization

TASK 12 converts verified football-data.co.uk staging values into canonical historical price
observations. TASK 12 stores historical price observations, not model probabilities. TASK 12 does
not calculate edge.

## Real inventory and supported mapping

The verified scope contains 4,460 canonical matches across fourteen competition/season sources.
The idempotency audit left 8,920 staging rows: two byte-identical staging lineages per canonical
match. Normalization verifies replay hashes and deterministically uses the earliest staging lineage;
4,460 replay copies are counted and ignored rather than persisted twice.

All fourteen representative sources contain nonblank `B365H`, `B365D`, `B365A`, `B365CH`,
`B365CD`, and `B365CA` values for every match. That is 26,760 supported values with zero missing,
malformed, non-finite, or `<= 1` prices. The source/season row counts are:

| Source | Season | Rows | Each supported field present | Missing |
|---|---:|---:|---:|---:|
| D1 | 2024/25 | 306 | 306 | 0 |
| D1 | 2025/26 | 306 | 306 | 0 |
| E0 | 2024/25 | 380 | 380 | 0 |
| E0 | 2025/26 | 380 | 380 | 0 |
| F1 | 2024/25 | 306 | 306 | 0 |
| F1 | 2025/26 | 306 | 306 | 0 |
| P1 | 2024/25 | 306 | 306 | 0 |
| P1 | 2025/26 | 306 | 306 | 0 |
| SC0 | 2024/25 | 228 | 228 | 0 |
| SC0 | 2025/26 | 228 | 228 | 0 |
| SP1 | 2024/25 | 380 | 380 | 0 |
| SP1 | 2025/26 | 380 | 380 | 0 |
| T1 | 2024/25 | 342 | 342 | 0 |
| T1 | 2025/26 | 306 | 306 | 0 |

The raw rows also expose season-varying bookmaker, exchange, source-average, and source-maximum
fields for 1X2, 2.5 totals, and Asian handicap markets. Examples include `AvgH`, `MaxH`,
`Avg>2.5`, `Max>2.5`, `P*`, `BFE*`, `WH*`, `BW*`, and their `C` closing variants. These are
inventoried but intentionally unsupported by normalization v1 pending individual semantic and
quality review. No explicit BTTS, team-total, or Double Chance columns were found. The `1XB*`
prefix identifies a bookmaker family and is not a Double Chance market.

Implemented mappings are deliberately limited to:

| Field | Source kind | Identity | Market | Selection | Line | Role | Timing |
|---|---|---|---|---|---|---|---|
| B365H | bookmaker | BET365 | match_result | home | NULL | source_prematch | role_only |
| B365D | bookmaker | BET365 | match_result | draw | NULL | source_prematch | role_only |
| B365A | bookmaker | BET365 | match_result | away | NULL | source_prematch | role_only |
| B365CH | bookmaker | BET365 | match_result | home | NULL | closing | role_only |
| B365CD | bookmaker | BET365 | match_result | draw | NULL | closing | role_only |
| B365CA | bookmaker | BET365 | match_result | away | NULL | closing | role_only |

Football-data documents its first set as collected after market opening and fields containing `C`
as closing odds. Exact quote timestamps are not supplied in the preserved match rows.

## Price and source semantics

Prices are parsed directly to `Decimal`; values are never clamped, filled, inferred, or silently
rounded. Missing, malformed, non-finite, and decimal odds not greater than one are explicit
diagnostics and are not persisted.

Bookmaker observations retain canonical bookmaker identity. Source averages and source maxima are
not bookmakers. They must use `source_average` or `source_maximum` with a null bookmaker if enabled
by a later mapping version. They are not PitchValue consensus or best-available prices. Consensus,
best-price, and reference-market derivation remain deferred.

## Temporal semantics

A historical bookmaker price is not automatically available at every earlier prediction_as_of.
Import time is not bookmaker observation time. File modification time is not bookmaker observation
time. Staging and runtime timestamps are not quote timestamps.

The supported rows preserve `observed_at = NULL`. Pre-closing fields use `source_prematch` and
closing fields use `closing`; both use `role_only`. A pure availability helper returns `UNKNOWN`
for role-only and unknown timing, so these values cannot silently pass an early prediction cutoff.
Only `exact` observations with an actual source timestamp may be compared using
`observed_at <= prediction_as_of`. TASK 13 remains the leakage authority.

## Quality, lineage, and versions

Quality is orthogonal to timing and uses `eligible`, `suspect`, `excluded`, or `invalid` plus stable
reason tokens. Timestamp uncertainty is recorded as `timestamp_uncertain`. The versioned
football-data Pinnacle policy marks observations on or after 2025-07-23 suspect; it is covered by
synthetic tests but is not exercised by the current Bet365-only real mapping. Raw staging values
are never deleted or changed.

Every observation links to its exact staging row and source field. Staging already links to import
batch, raw identity, and registered source. Versions are fixed identifiers:

- `football_data_mapping_v1`
- `historical_odds_normalization_v1`
- `football_data_quality_v1`

The DB partial unique identity combines staging row, source field, and all three versions. Inserts
use atomic conflict handling, so rerunning the same interpretation reuses existing observations.

## Responsibility boundaries

TASK 11 remains the sole owner of implied probability, overround, and no-vig mathematics. Those
values are not persisted by TASK 12. Double Chance is not fabricated or grouped as an exclusive
market.

TASK 15 remains `FOOTBALL_PERFORMANCE_ONLY` by default. Historical prices may enter only a future,
separate `ODDS_INCLUSIVE_EXPERIMENT`; normalization does not inject them into ML datasets.

TASK 16–20 remain deferred: no ML training, calibrator fitting, ensemble, edge/EV/ROI/Kelly,
Bet Score, publication, selection policy, sportsbook action, or settlement is implemented here.
