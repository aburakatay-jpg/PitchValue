# Feature Engine

The feature engine computes deterministic pre-match football features from a target fixture, an explicitly supplied collection of canonical matches, and immutable feature configuration. It prepares meaningful typed inputs for future models without implementing a prediction model, accessing a database, persisting features, or publishing picks.

Initial feature windows are engineering defaults subject to backtest validation. No predictive value is claimed.

## Pure computation and contracts

`TargetFixture` contains identifiers, teams, kickoff, and an optional `as_of` cutoff; it has no score, result, label, odds, or post-match fields. `HistoricalMatch` contains canonical normal-time score data and an optional statistics contract. `compute_match_features` has no database, HTTP, current-time, randomness, environment, logging, or mutable-cache behavior. Identical inputs and configuration produce identical output.

The typed output groups target metadata, home-team features, away-team features, a league baseline, raw venue scoring rates, and lightweight filtering diagnostics. `to_dict()` produces deterministic primitive values, using ISO timestamps and strings for exact Decimals, without writing files.

## History eligibility and temporal leakage

For cutoff `T`, a historical row is eligible only when its kickoff is strictly earlier than `T`. `as_of` defaults to target kickoff and cannot be after kickoff. Match kickoff is the TASK 06 approximation for when completed match information became available; future injury, lineup, event, and odds sources will require their own availability timestamps.

The target match is excluded. A target ID deceptively timestamped before the cutoff is rejected. Matches after the cutoff and matches at exactly the cutoff are excluded. Same-time exclusion is the conservative default because kickoff ordering does not prove that a result was available. Target scores, future scores, results, outcome labels, post-kickoff information, closing movements, and odds are never feature inputs.

History is sorted by kickoff and then `match_id`, independent of caller ordering. Duplicate historical match IDs are rejected rather than double-counted.

## Competition, season, and status scope

Features are competition-scoped. Other leagues, domestic cups, UEFA competitions, and any other competition are excluded even when team IDs overlap.

The default season policy is `CURRENT_SEASON_ONLY`. `CURRENT_AND_PREVIOUS_SEASON` is available only when the caller explicitly names the previous season ID; season ordering is never inferred from identifiers. Promoted or new teams therefore remain partial or unavailable instead of receiving manufactured priors.

Only `FINISHED` matches with paired, non-negative canonical normal-time scores contribute. Extra-time and penalty scores are not represented or reinterpreted. `AWARDED` matches are conservatively excluded from sporting-form features. Scheduled, postponed, abandoned, cancelled, and other non-finished rows are excluded. A finished match without scores is invalid input.

## Rolling team form

The centralized defaults are marked **INITIAL FEATURE WINDOW — SUBJECT TO BACKTEST VALIDATION**:

- Recent overall form: 5 matches
- Extended overall form: 10 matches
- Target home-team home split: 5 home matches
- Target away-team away split: 5 away matches
- Schedule density: previous 7 and 14 days

For recent and extended form, and for the venue split, the engine computes matches, wins, draws, losses, points, points per game, goals for and against, their per-game rates, goal difference and its rate, clean sheets and rate, failed-to-score count and rate, BTTS count and rate, and over-1.5 and over-2.5 counts and rates. Standard points are 3/1/0.

One canonical perspective helper reverses goals and results for the away team. BTTS means both normal-time scores are positive. Over 1.5 means integer total goals are at least 2; over 2.5 means at least 3.

Home splits use only matches where the target home team was home. Away splits use only matches where the target away team was away. Their goals-for and goals-against rates, plus league home/away scoring baselines, are exposed as raw future-Poisson inputs. No attack strength, defence strength, lambda, or probability is calculated.

## Rest and schedule density

Rest uses the immediately preceding eligible match for each target team and reports its kickoff and exact Decimal days to target kickoff. With no prior match, both values remain unavailable.

Schedule counts use the interval:

`target kickoff - N days <= prior kickoff < target kickoff`

The lower boundary is inclusive and the target boundary is exclusive. Counts are facts only; no fatigue score is invented.

## League baseline

Using all eligible competition-and-season-scoped history, the engine calculates matches played, home/away goals per match, total goals per match, home/draw/away rates, BTTS rate, and over-2.5 rate. These are raw aggregates only and do not constitute a Poisson model.

## Missing data and coverage

Each rolling group exposes requested matches, available matches, minimum observations, and one state:

- `COMPLETE`: the requested rolling window is filled.
- `PARTIAL`: at least one but fewer than the requested matches are available.
- `UNAVAILABLE`: no applicable history exists.

League coverage is complete once the configured minimum observation count is met and partial below it. Counts such as zero goals in known matches remain true zeros. With no observations—or fewer observations than configured for derived rates—rates remain `None`; absence is never silently converted to zero. Partial groups are returned rather than rejected so a future data-quality layer can evaluate coverage.

Optional shots, shots on target, corners, and fouls are represented but not required or aggregated in the core score feature vector. Missing statistics remain missing. This engine exposes coverage facts and does not calculate the TASK 05 normalized data-quality score.

## Configuration and diagnostics

`FeatureConfig` is frozen and validates positive rolling windows, recent not exceeding extended, positive ordered unique density windows, a usable minimum-observation threshold, and explicit previous-season context. Tests can create immutable overrides without global mutation.

Diagnostics report received and eligible rows plus target, future, same-time, different-competition, different-season, awarded, and non-finished exclusions. They contain counts rather than historical payloads.

## Explicitly deferred

Poisson strengths and lambda, Elo, xG, advanced shot/statistical aggregation, cross-competition form, head-to-head, promoted-team priors, odds and market features, odds normalization, data-quality scoring, an ML flattening/vector adapter, model training, ensemble and calibration work, persistence, bulk feature generation, prediction publication, API endpoints, and backtesting are not implemented.
