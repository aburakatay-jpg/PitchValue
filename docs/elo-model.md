# Elo Rating Foundation

PitchValue Elo is a deterministic, venue-aware relative-strength signal for future modeling. It initializes ratings, calculates pre-match expectations, updates ratings after ordinary completed matches, replays explicit season histories, and produces leakage-safe target snapshots. It is not connected to publication policy, APIs, persistence, real historical replay, or predictions.

All values below are **INITIAL ELO PARAMETERS — SUBJECT TO BACKTEST CALIBRATION**. No model accuracy or calibration is claimed.

## Formula and initial parameters

Default configuration:

- Initial and league-baseline rating: 1500
- K factor: 20
- Rating scale: 400
- Home advantage: 100 Elo points
- Season regression factor: 0.75
- Goal-margin adjustment: disabled

For stored ratings `R_home` and `R_away`, effective home rating is `R_home + home_advantage`. The standard two-team expectation is calculated from the home-adjusted rating difference and configured scale. Expected home and away scores are exact complements and sum to one.

The exponentiation operation is isolated in one function using Python float mathematics, then converted through a stable decimal string. All surrounding state, adjustments, regression, and exported values use `Decimal`.

## Interpretation

Elo expectation is a continuous relative-strength expectation for rating updates and downstream model features. Football includes draws, so this output is **not** a calibrated home-win probability, away-win probability, or 1X2 distribution. No fixed or inferred draw probability is added.

Home advantage changes only match expectation. It does not change the actual result score and is never added to stored venue-neutral team ratings.

## Match results and updates

Canonical normal-time results map to home actual scores of 1 for a home win, 0.5 for a draw, and 0 for an away win. Extra time and penalties are not inputs. The base adjustment is:

`K × goal_margin_multiplier × (actual_home - expected_home)`

The home team gains the adjustment and the away team loses exactly the same value, preserving the ordinary match rating pool. A favorite drawing loses rating to the underdog; an upset produces a larger change than an expected favorite win.

Goal-margin adjustment is disabled by default, so 1–0 and 5–0 have identical impact from identical pre-match states. An optional provisional bounded strategy is isolated behind configuration: each goal beyond a one-goal margin adds 0.25, capped at 1.50. This optional behavior is also subject to backtest calibration.

Ratings have no arbitrary floor or ceiling.

## Replay and pre-match snapshots

Replay accepts caller-supplied canonical TASK 06 match contracts and never accesses the database. It validates duplicate IDs, filters matches, sorts by kickoff then match ID, captures optional snapshots before each update, and returns sorted immutable final team states, cumulative match counts, diagnostics, and optional audit snapshots.

Only `FINISHED` matches with valid normal-time scores in the requested competition and strictly before `as_of` are processed. Target, future, same-time, `AWARDED`, and other non-finished matches are ignored. A target ID deceptively timestamped before the cutoff is rejected. Input collections and match objects are not mutated.

Target output includes stored home and away pre-match Elo, raw stored-rating difference, effective home Elo, home-adjusted difference, complementary expected scores, prior update counts, and the exact cutoff. The target result and later results cannot affect this snapshot.

## Competition and season scope

Elo replay is competition-scoped. Domestic league, cup, UEFA, and other competition histories never mix automatically. Cross-competition or global club Elo requires a separate future design.

Season chronology is an explicit ordered tuple supplied by the caller. IDs are never parsed or guessed. The first observed season uses initial ratings without regression. On each explicit forward season change, every established rating is regressed once:

`new = baseline + factor × (old - baseline)`

Factor 1 carries ratings fully, factor 0 resets established ratings to the baseline, and intermediate factors partially regress them. The default baseline is the initial rating. A target-season transition can occur without using the target result.

Previously unseen teams always receive the configured initial rating and a prior match count of zero. No promoted-team, relegation, league-strength, market-value, transfer, or UEFA priors exist.

## Leakage and determinism

The engine has no database, HTTP, current-time, randomness, environment, logging, persistence, or global mutable state. Same inputs and configuration return the same values. Shuffled history produces identical replay. Pre-match snapshots are captured before their match result is applied. Synthetic target and extreme future results are verified not to change the target snapshot.

## Deferred work

Football 1X2 Elo calibration, draw probability modeling, dynamic K, goal-margin calibration, promoted-team priors, cross-competition/global Elo, Poisson, ML, ensemble and calibration integration, historical backtesting, feature orchestration, API integration, publication integration, and database persistence remain deferred.
