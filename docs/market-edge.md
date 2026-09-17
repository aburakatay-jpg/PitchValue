# TASK 19 market implied probability, edge, and value diagnostics

RAW TASK 16 ML is the accepted model probability source. The rejected TASK 17
calibrated candidate and rejected TASK 18 ensemble are not used.

## Mathematics and contracts

TASK 19 supports Bet365 `MATCH_RESULT` groups with exactly one `HOME`, `DRAW`, and
`AWAY` price. Decimal prices are validated by TASK 11. Raw implied probability is
`1 / decimal odds`; book percentage is the three-way sum, and margin/overround is
that sum minus one. TASK 11's versioned proportional no-vig abstraction produces
the canonical market probabilities. TASK 19 does not duplicate or persist this
market math.

Canonical edge is model probability minus no-vig market probability. Edge is a
probability-point difference, not relative uplift, realized ROI, or guaranteed
return. The optional `raw_price_ev = model_probability * decimal_odds - 1` is a
mathematical model-implied price diagnostic only. It is not a staking or
profitability result.

Every immutable result retains model/version/profile, prediction time,
bookmaker, observation role, timing semantics, no-vig version, normalization and
quality-policy versions, exact source field, staging row, and canonical provider
reference. All three selections are evaluated. `best_edge_selection` is neutral
engineering metadata and is not a pick.

## Temporal honesty

Historical role-only odds are not assumed to have been available at prediction_as_of.

The model `prediction_as_of` is known exactly at kickoff minus 24 hours. The
historical Bet365 market role is known, but `observed_at` is null. Import time,
staging time, file modification time, and runtime time are never substituted.

`source_prematch` is a `SOURCE_PREMATCH_ROLE_REFERENCE`; it does not prove that
the quote was available at T-24. Closing odds are used only as a reference diagnostic and are not treated as information available to the T-24 model.

Accordingly, model leakage safety is PASS while exact market timestamp alignment
is NOT PROVEN. Both current roles have `ROLE_ONLY_COMPARISON`, never
`EXACT_TIME_COMPARISON`.

## Real historical evaluation

The read-only evaluation used all 2,701 RAW ML OOS rows. Both source-prematch and
closing had 2,701 complete eligible groups; there were no missing, invalid,
quality-excluded, incomplete, or ambiguous aligned groups.

| Role              | Predictor     |    Log Loss |       Brier | Accuracy |    ECE-like |
| ----------------- | ------------- | ----------: | ----------: | -------: | ----------: |
| source_prematch   | RAW ML        | 1.001186878 | 0.597546781 | 50.9071% | 0.026982994 |
| source_prematch   | market no-vig | 0.966402896 | 0.574258663 | 54.2182% | 0.016604981 |
| closing reference | RAW ML        | 1.001186878 | 0.597546781 | 50.9071% | 0.026982994 |
| closing reference | market no-vig | 0.964440105 | 0.572883707 | 54.5387% | 0.023452944 |

Model-minus-market deltas were +0.034783981 Log Loss and +0.023288117 Brier for
source-prematch, and +0.036746773 Log Loss and +0.024663073 Brier for closing.
These comparisons describe role references; they are not fair same-time market
competitions.

The market beats RAW ML on these same-row probability metrics, but this does not establish exact prediction-time market superiority. Positive or high edge counts do not establish profitable value.

Across 8,103 selection-level comparisons per role, source-prematch had 4,306
positive edges, 794 edges from 4% to below 6%, no edge exactly 6%, and 1,412 over
6%. Closing had 4,296 positive edges, 755 from 4% to below 6%, no edge exactly
6%, and 1,529 over 6%. Because each no-vig and model vector sums to one, mean edge
across all three selections is mathematically approximately zero; distribution
and selection slices are more informative than the aggregate mean.

Positive edge was concentrated more heavily in DRAW and AWAY than HOME. The
`>3.00` odds band contained most positive-edge observations, while lower-price
bands had negative mean edge. These are descriptive diagnostics only. Raw ML is
uncalibrated, so edge estimates inherit model calibration error.

## Threshold and product boundaries

Threshold labels are diagnostic only:

- below 0.04: `BELOW_THRESHOLD`
- 0.04 to below 0.06: `WATCHLIST_EDGE`
- 0.06 or greater: `PUBLISHABLE_EDGE`

These labels do not issue a final decision. Odds presentation bands similarly do
not alter implied probability, no-vig probability, or edge.

TASK 19 does not calculate Bet Score or issue final Pick/No Bet decisions.
It does not implement Kelly staking, realized ROI, settlement, CLV, publication,
or sportsbook behavior. TASK 20 owns orchestration and policy integration.
