# TASK 18 evidence-based ensemble

TASK 18 evaluates a single, deliberately small probability-ensemble candidate for
`MATCH_RESULT`: raw TASK 16 multinomial ML plus raw TASK 08 Poisson.

Ensemble complexity is not assumed to improve predictions.

## Input semantics and scope

Raw ML and raw Poisson provide explicit, uncalibrated `HOME`, `DRAW`, `AWAY`
probability vectors. Elo and Form strength signals are not treated as calibrated probabilities.
They remain agreement diagnostics only, and no probability mass is
fabricated for either signal. NEUTRAL is not DRAW.

The rejected TASK 17 calibrated ML output is not used as an ensemble input. The
candidate uses the unchanged TASK 16 model, football-performance-only feature
profile, 24-hour prediction horizon, and canonical class order.

Historical bookmaker odds are not used to select ensemble weights.

TASK 18 does not calculate edge. It also does not calculate EV, Kelly, ROI, CLV,
Bet Score, settlement, or publication decisions, and it does not persist model
predictions.

## Contract and alignment

The immutable prediction contract records row and match identity,
`prediction_as_of`, target market, model family/version, canonical class order,
probabilities, and any explicitly unallocated Poisson matrix mass. The ensemble
contract adds its stable `ml_poisson_linear_blend_v1` version, contributing model
weights, prior evidence support and cutoff, status, and diagnostics.

Only identical row, match, `prediction_as_of`, `MATCH_RESULT` target, and class
ordering may be blended. Invalid vectors are rejected rather than normalized.
Poisson residual mass remains explicit and is carried through the linear blend.

## Temporal weight selection

The deterministic grid is `w_ml = 0.0, 0.1, ..., 1.0`, with
`w_poisson = 1 - w_ml`. A future fold's weight is selected by minimum Log Loss,
then Brier, then the lower ML weight as deterministic tie-breaker, using only
matched OOS observations strictly before that fold. A fold cannot choose its own
weight. Fewer than 200 prior matched OOS rows returns
`INSUFFICIENT_ENSEMBLE_SUPPORT`; there is no silent 50/50 fallback.

Fixed 0/25/50/75/100 percent ML weights are diagnostic benchmarks only and are
not used as an unbiased production choice.

## Real historical evaluation

The read-only run used the canonical domestic database at Alembic
`20260910_0007`, TASK 13 expanding walk-forward chronology, and the same TASK 16
OOS rows. It generated 2,701 raw ML OOS rows. Poisson was valid and aligned for
2,377 rows; 324 rows were excluded with explicit input or probability diagnostics.
The initial 238-row fold supplied evidence but could not itself receive a selected
weight. Later temporal ensemble metrics therefore cover 2,139 identical rows.

On those 2,139 rows:

| Candidate | Log Loss | Brier | Accuracy | ECE-like |
| --- | ---: | ---: | ---: | ---: |
| Raw ML | 1.0105023510 | 0.6040749632 | 49.3221% | 0.0286645493 |
| Raw Poisson | 1.9563299043 | 0.6875591772 | 45.8626% | 0.1063005506 |
| Temporal ensemble | 1.0105023510 | 0.6040749632 | 49.3221% | 0.0286645493 |
| Training prior | 1.0770238860 | 0.6516305604 | 43.3848% | 0.0137618367 |

Every one of the 11 weight-selected folds chose `w_ml=1.0` and
`w_poisson=0.0`; min, median, and max ML weight were all 1.0, and all 11 solutions
were boundary solutions. The temporal ensemble consequently equals raw ML on
every evaluated row. The first matched fold had insufficient prior ensemble
support; two additional planned windows were unsupported because one had too few
test observations and one was empty.

The diagnostic all-matched-row fixed-weight results also improved monotonically
toward raw ML: Log Loss was 1.9016366884 at ML=0, 1.0870473976 at 0.25,
1.0431192928 at 0.50, 1.0189235432 at 0.75, and 1.0090782067 at ML=1.0.

## Robustness and signal diagnostics

The temporal result equaled raw ML in all seven competitions and both seasons,
so the ensemble introduced neither a gain nor an additional class-specific
change. Its signed calibration gaps were -0.03234 HOME, +0.00415 DRAW, and
+0.02819 AWAY. Poisson was worse in aggregate and in every competition slice on
Log Loss.

Elo/Form diagnostics remained non-probabilistic. Ensemble/ML Log Loss was lower
when their directions supported the ML top class than when they conflicted:
Elo support 0.97000 versus conflict 1.12263; Form support 0.98923 versus conflict
1.06234. This is descriptive subgroup evidence only; no gating or probability
modifier was fitted.

## Decision

The engineering decision is `ENSEMBLE_CANDIDATE_REJECT`.

RAW ML remains the preferred probability model. Repeated boundary selection demonstrates that
Poisson did not earn non-zero weight under this evaluation. TASK 19 may consume
the selected raw ML policy only after its own authorization; no market comparison
or publication behavior is part of TASK 18.
