# Form and performance signal

The form model converts the leakage-safe, pre-match aggregates produced by the TASK 06 feature engine into an auditable relative performance signal. It does not read match history, the database, odds, Elo, Poisson output, or target outcomes.

Form scores are relative performance indices, not calibrated outcome probabilities. A score of 70 means a stronger form index than 50; it does not mean a 70% chance of winning. The model does not create home/draw/away probabilities, final predictions, picks, or publication decisions.

## Architecture

`FormModelConfig` owns all thresholds, bounds, weights, and missing-data choices. Scoring functions normalize individual inputs and return component diagnostics. `analyze_form_signal` composes those pure component results into immutable team and match-level contracts. Identical `MatchFeatures` plus configuration produce identical output, with no time, random, network, persistence, or mutable-global dependency.

The input is exclusively a TASK 06 `MatchFeatures` instance. That contract contains outcome-free target metadata and aggregates calculated strictly before the feature cutoff, so TASK 09 has no history or target-result parameter through which it could introduce lookahead.

## Initial components and weights

**INITIAL FORM SIGNAL WEIGHTS — SUBJECT TO BACKTEST CALIBRATION.**

The engineering defaults are:

| Component             | Weight | Inputs                                                                   |
| --------------------- | -----: | ------------------------------------------------------------------------ |
| Recent overall form   |    25% | Recent PPG and goal difference per match                                 |
| Extended overall form |    15% | Extended-window PPG and goal difference per match                        |
| Venue form            |    25% | Home split for the target home team; away split for the target away team |
| Attack performance    |    15% | Recent and venue goals scored relative to league baselines               |
| Defensive performance |    15% | Recent and venue goals conceded relative to league baselines             |
| Schedule/rest context |     5% | Rest days and 7-/14-day match counts                                     |

All component outputs and final team scores use a 0–100 strength-index scale with 50 as neutral/reference. Available component weights are re-normalized; missing components are never silently entered as zero.

## Normalization

PPG uses the transparent football range `PPG / 3 × 100`. Goal difference per game uses a bounded linear mapping whose default endpoints are -2 → 0, 0 → 50, and +2 → 100. The recent and extended form components weight normalized PPG at 70% and normalized goal difference at 30%.

Attack compares scoring rate with the relevant league scoring baseline. A ratio of 0 maps to 0, league average (1) maps to 50, and 2 or above maps to 100. Defense uses conceded-rate ratios in the opposite direction: zero conceded maps to 100, league average maps to 50, and a ratio of 2 or above maps to 0. Thus a higher defense score always means better defensive performance.

Recent and venue performance inputs have default inner weights of 40% and 60%. If only one valid input exists, that input is used with an explicitly partial coverage state and the available inner weight is re-normalized.

## Schedule context

Schedule starts from the neutral score of 50. Less than four days' rest receives a bounded penalty; seven or more days receives a small capped bonus. Match counts above the configured 7- and 14-day congestion thresholds receive simple linear penalties, and the component is bounded to 20–60. This low-weight rule is an engineering context signal, not a medical fatigue model.

Missing rest is unavailable by default, not neutral or rested. The default missing-component policy excludes it and re-normalizes the remaining team weights. An explicit `NEUTRAL_IMPUTE` configuration is available for controlled experiments and marks the component reason as `NEUTRAL_IMPUTED`.

## Coverage and readiness

TASK 06 coverage states remain visible:

- `COMPLETE`: the requested feature window is complete.
- `PARTIAL`: a numeric aggregate exists from less than the requested window.
- `UNAVAILABLE`: no usable aggregate exists.

The default policy uses partial numeric evidence and exposes it in component and team coverage metadata. A configurable conservative policy can exclude partial components. Unavailable values are excluded rather than converted to zero.

A team is ready only when it has at least recent or extended overall form, venue form, at least one of attack or defense, and the configured minimum number of actual scored components (default four). Neutral imputation does not satisfy these core evidence requirements. Both teams must be ready for a match result to be `READY`; otherwise the result is `INPUT_INSUFFICIENT` and no relative score is emitted.

## Output and diagnostics

Each team result includes the six component scores, final weighted form score, component coverage counts, effective weight sum, reason codes, source values, and normalized values. Match output includes both team scores, raw `home - away` difference, and symmetric directional signals:

`home_relative_form_signal = raw_difference / 100`

The directional signal is bounded to -1 through +1. Positive values favor the home team's form, negative values favor the away team's form, and zero indicates equality. It is not a probability and has no generic home-advantage bonus; home/away context is already represented by venue splits.

Contracts serialize deterministically to primitive mappings. Decimal values serialize as strings so downstream audit logs do not introduce binary floating-point changes.

## Independence and limitations

TASK 09 deliberately does not mix Elo or Poisson results, use bookmaker odds, call prediction/publication policy, or persist output. Score/result aggregates only are used; shots, shots on target, corners, xG, injuries, and lineups are absent. The initial bounds and weights are transparent engineering defaults, not claims of accuracy, profitability, or calibration.

Deferred work includes probabilistic calibration, empirical parameter fitting, Elo and Poisson orchestration, an ML signal, model ensemble/agreement, backtesting, richer performance statistics, odds integration, publication policy integration, API exposure, and persistence.
