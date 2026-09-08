# Prediction Policy

The prediction policy is the deterministic boundary between future model evidence and publishable PitchValue output. Models will produce evidence; they will not publish picks directly. Given the same candidate and policy configuration, evaluation always returns the same result and performs no database, HTTP, time, random, environment, or telemetry work.

All defaults in this document are **initial V1 policy subject to backtest calibration**. They are foundation rules, not claims of predictive performance.

## V1 market contract

The policy accepts only these market families:

- `match_result`: `home`, `draw`, `away`; no line
- `total_goals`: `over` or `under`; line `1.5` or `2.5`
- `btts`: `yes` or `no`; no line
- `double_chance`: `1X`, `X2`, or `12`; no line
- `home_team_total`: `over` or `under`; line `0.5` or `1.5`
- `away_team_total`: `over` or `under`; line `0.5` or `1.5`

Corners, cards, first-half, correct-score, and player markets are outside V1.

## Numeric semantics and edge

Probabilities and edge use exact `Decimal` fractions from 0 to 1. Scores use exact `Decimal` values from 0 to 100. Decimal odds must be greater than 1. Binary floating-point inputs are rejected at the explicit conversion boundary.

Canonical edge is:

`model_probability - market_implied_probability`

For example, `0.56 - 0.50 = 0.06`: an edge of six percentage points, not a six-percent relative uplift. Edge below `0.04` is `NO_BET`; `0.04` up to but excluding `0.06` is a watchlist candidate; `0.06` or more is a publication candidate. Publication candidacy does not bypass any other gate.

## Bet Score

Each available component is validated in the 0–100 range. Missing components are not assigned fabricated values. The weighted score is:

| Component | Weight |
| --- | ---: |
| Edge Score | 35% |
| Model Agreement | 25% |
| Data Quality | 15% |
| Calibration Confidence | 15% |
| Market Stability | 10% |

Weights are configuration values and must total exactly 1.0.

The Edge Score uses an **INITIAL HEURISTIC — SUBJECT TO BACKTEST CALIBRATION**. It is piecewise linear through: non-positive edge = 0, `0.04` edge = 50, `0.06` edge = 70, and `0.12` edge = 100, with a cap of 100 thereafter. No empirical calibration is claimed.

Model agreement is `agreement_count / total_model_count`, and its component score is that ratio multiplied by 100. The current publication minimum is `0.75`, so 3/4 passes; equivalent non-four ensembles also work. Zero models means agreement is unavailable and prevents publication.

Data Quality has an initial minimum of 70. Calibration Confidence and Market Stability are policy inputs only: this layer does not calculate either value.

## Quality classes and publication gates

Quality classification is based only on a completed Bet Score:

- below 60: `NO_BET`
- 60 through 69.999…: `WATCHLIST`
- 70 through 79.999…: `PICK`
- 80 through 89.999…: `STRONG_PICK`
- 90 through 100: `ELITE_PICK`

Quality and storefront publication are separate. A candidate may publish only if all hard gates pass: edge at least `0.06`, Bet Score at least 70, agreement ratio at least `0.75`, Data Quality at least the configured minimum, every required analysis component is available, and its odds band permits the requested role. A failed hard gate cannot be averaged away.

## Odds policy

- Below `1.35`: neither main nor alternative publication is eligible by default.
- `1.35` through `1.49…`: never a main pick; alternative eligibility requires the provisional exceptional rule of Bet Score at least 85, edge at least `0.08`, and agreement at least `0.90`, in addition to all base gates.
- `1.50` through `2.20`: ideal main-pick band.
- `2.21` through `3.00`: higher-risk band; publication is allowed when every base gate passes.
- Above `3.00`: not eligible as a V1 main pick and currently receives no publication role, while its analytical quality class is preserved for internal use.

Every bound and exceptional threshold is centralized in the immutable policy configuration.

## Failure states and reasons

`DATA_INSUFFICIENT` means required football or data-quality input is absent. `ANALYSIS_UNAVAILABLE` means required model/analysis output is missing or explicitly unavailable. `NO_BET` means analysis completed, but policy does not support publication. An eligible result has no failure state.

Deterministic reason codes are:

- `EDGE_BELOW_MINIMUM`
- `EDGE_WATCHLIST_ONLY`
- `BET_SCORE_BELOW_PUBLICATION`
- `MODEL_AGREEMENT_INSUFFICIENT`
- `DATA_QUALITY_INSUFFICIENT`
- `DATA_QUALITY_MISSING`
- `CALIBRATION_CONFIDENCE_MISSING`
- `MARKET_STABILITY_MISSING`
- `ANALYSIS_UNAVAILABLE`
- `ODDS_BELOW_DISPLAY_MINIMUM`
- `LOW_ODDS_REQUIRES_STRONGER_SIGNAL`
- `ODDS_ABOVE_V1_MAIN_MAX`
- `PUBLISHABLE`

## Future ranking and correlation

Evaluation exposes Bet Score, edge, agreement, market stability, odds usability, and an optional caller-supplied correlation/exclusion group. These are inputs for a future same-match ranker; this task does not select winners and does not encode “highest edge wins.” V1 contracts cap future output at one Main Pick and one Alternative Pick per match. A future ranker can use correlation groups to suppress redundant markets without pretending this layer models statistical correlation.

The evaluation result also exposes a structured decision record containing the candidate identity, edge, score, class, role eligibility, reasons, failure state, odds band, and correlation group. Callers may log it; pure policy functions do not emit logs themselves.

## Configuration strategy

`PredictionPolicyConfig` is a frozen, nested dataclass with explicit `Decimal` fields. Construction rejects unordered thresholds, invalid normalized limits, weights that do not total 1.0, inconsistent odds bands, and impossible low-odds exception rules. Tests can use immutable replacements without mutating the shared default. The configuration serializes to a safe string-valued debug representation and is product/model policy, not deployment-secret environment configuration.

## Not implemented

This foundation does not implement Poisson, Elo, form features, feature extraction, machine learning, probability ensembles, calibration fitting, a market-stability model, historical backtesting, persistence, API routes, real picks, football business logic, LLM behavior, or UI behavior.
