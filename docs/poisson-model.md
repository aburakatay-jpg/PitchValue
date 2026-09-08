# Poisson Goal-Model Foundation

PitchValue’s Poisson foundation is a deterministic mathematical model signal. It consumes pre-match venue scoring rates, derives expected home and away goals, constructs an auditable finite score matrix, and derives the supported V1 market probabilities. It does not read history, train parameters, consume odds, publish picks, or integrate with Elo or TASK 05 policy.

**Poisson outputs are model probabilities, not final PitchValue picks.** No accuracy, profitability, calibration quality, or predictive superiority is claimed.

## Inputs and strength formula

Required inputs are:

- Home team home goals scored per match
- Home team home goals conceded per match
- Away team away goals scored per match
- Away team away goals conceded per match
- League home goals per match
- League away goals per match

The optional adapter reads these values only from TASK 06’s pre-match `MatchFeatures.raw_scoring_rates` and preserves venue/league coverage metadata. It never accesses match history and does not mutate feature output.

The **INITIAL POISSON STRENGTH FORMULA — SUBJECT TO BACKTEST CALIBRATION** is:

- Home attack strength = home-team home GF rate / league home GF rate
- Home defensive weakness = home-team home GA rate / league away GF rate
- Away attack strength = away-team away GF rate / league away GF rate
- Away defensive weakness = away-team away GA rate / league home GF rate
- Home lambda = league home GF rate × home attack strength × away defensive weakness
- Away lambda = league away GF rate × away attack strength × home defensive weakness

A defensive factor above one means more goals conceded than the applicable league baseline: it is explicitly a weakness, not an ambiguously named strength. League home/away baselines already encode structural venue effects, so no additional Elo-style home advantage is added.

True team rates of zero are valid and may produce lambda zero. Missing rates are not replaced by league averages or priors. Non-finite, negative, or non-Decimal rates and zero/non-positive league baselines are rejected.

## Status and coverage

Ready input produces `READY`. Missing required analytical rates or a configured coverage-policy failure produces `INPUT_INSUFFICIENT` without a matrix or probabilities. `INVALID_INPUT` is reserved in the model status contract; malformed programming inputs and invalid configuration raise `PoissonValidationError` at construction/calculation boundaries rather than being converted into plausible analytical output.

The default partial-history policy is `ALLOW_PARTIAL`: valid partial venue rates may be analyzed and the diagnostic records that partial history was used. `REQUIRE_COMPLETE` is available for conservative callers. TASK 08 does not decide how partial coverage maps to TASK 05 data quality.

## Numeric strategy and lambdas

Rates, strengths, lambdas, matrix cells, masses, and market outputs use `Decimal`. The Poisson exponential/log-gamma operation is isolated inside the PMF function using standard-library float math, then converted back through a stable decimal string. This is deterministic finite-precision probability arithmetic, not arbitrary-precision transcendental math.

Lambdas must be non-negative. No lambda is clamped. The configuration instead provides an explicit combined analytical ceiling of 50; input producing a larger combined lambda is rejected. This limit is an engineering safeguard and is subject to validation.

## Score matrix and tail mass

The independent score matrix contains every home/away score from zero through the configured maximum. The **INITIAL SCORE-MATRIX TRUNCATION — SUBJECT TO VALIDATION** is 10 goals per team. Every cell is the product of the two independent marginal PMFs.

The matrix exposes both represented probability mass and residual tail probability. It is never silently renormalized. Increasing the goal limit cannot reduce represented mass. Exact-score lookup exists for internal audit/model support only; Correct Score is not added as a V1 product market.

## Market probabilities

The 1X2 signal is partitioned from the finite matrix:

- Home: cells where home goals exceed away goals
- Draw: cells where goals are equal
- Away: cells where away goals exceed home goals

Their sum equals represented matrix mass and may be slightly below one by the disclosed residual tail. Double Chance is derived directly from these values: 1X = home + draw, X2 = draw + away, and 12 = home + away.

Other markets avoid matrix truncation:

- Over/Under 1.5 and 2.5 use the exact independent-Poisson sum property with total lambda = home lambda + away lambda.
- BTTS YES uses `1 - P(home=0) - P(away=0) + P(0,0)`; NO is its complement.
- Home and away team totals use their marginal PMFs directly for 0.5 and 1.5 lines.

Complementary marginal markets sum to one within the deterministic numeric representation. All exported probabilities are guaranteed within [0,1]. Market and selection identifiers reuse TASK 05 canonical contracts, but no publication-policy function is called.

## Pure-operation boundary

The model has no database, HTTP, current time, randomness, environment configuration, persistence, logging side effects, or mutable global state. Identical immutable input and configuration return identical output. TASK 06 determines rolling history and recency; this layer adds no hidden time decay or historical replay.

## Limitations and deferred work

The independent-Poisson assumption does not model score correlation or special low-score effects. Dixon–Coles correction, bivariate Poisson, zero inflation, time decay, xG adjustment, new-team priors, empirical parameter calibration, football 1X2 calibration, Elo integration, ML, ensembles, backtesting, publication integration, API integration, and persistence remain deferred.
