# Market odds and implied probability mathematics

TASK 11 defines provider-agnostic price contracts and pure market mathematics. It accepts synthetic Decimal bookmaker prices and produces auditable raw implied probabilities, complete-market book percentage, overround, and no-vig probabilities. It does not load historical data, select bookmakers, compare prices with models, or compute betting value.

## Decimal odds

Decimal odds are the only internal V1 odds representation. Values must be Decimal, finite, and strictly greater than 1. Zero, one, negative values, infinities, NaN, floats, strings, and malformed values are rejected rather than silently coerced.

Mathematically valid odds are not filtered by storefront display bands. TASK 11 does not apply publication rules such as minimum or preferred odds.

## Raw implied probability

The source-price conversion is:

raw implied probability = 1 / decimal odds

Calculations use a local Decimal context with configurable precision and are not rounded for display. Raw implied probability is not the same thing as no-vig market probability. The raw value still contains the bookmaker margin when considered as part of a complete market.

Individual raw calculation does not require market completeness. For example, a single Double Chance 1X price has a valid raw implied probability even though the three Double Chance selections cannot be normalized together as exclusive outcomes.

## Book percentage and overround

For one complete, mutually exclusive source market:

book percentage = sum of raw implied probabilities

overround = book percentage - 1

These are distinct fields. A book percentage of 1.06 has overround 0.06. A fair synthetic market may have both 1 and 0 respectively.

An underround market has book percentage below 1 and negative overround. TASK 11 preserves that negative value and can still apply mathematically defined proportional normalization. It does not clip, repair, or alter the source odds.

## No-vig architecture

No-vig method is an explicit immutable configuration value. PROPORTIONAL is implemented. SHIN, POWER, and ADDITIVE are reserved method identifiers only; requesting them returns UNSUPPORTED_NORMALIZATION_METHOD and never silently falls back.

Proportional margin removal is the initial baseline method and is subject to future validation. No-vig methodology is a market-math assumption. Later empirical validation may choose another method without renaming the raw, book, overround, or no-vig contracts.

For a complete mutually exclusive market:

no-vig probability for selection i = raw implied probability i / book percentage

The resulting probabilities sum to one within the configured Decimal tolerance. Decimal odds and raw probabilities remain beside no-vig values in the output; normalization never overwrites source evidence.

## Complete and incomplete markets

The central typed registry defines canonical selection order, allowed lines, and exclusivity:

| Market          | Required selections | Line       | Exclusive |
| --------------- | ------------------- | ---------- | --------- |
| Match Result    | HOME, DRAW, AWAY    | none       | yes       |
| Total Goals     | OVER, UNDER         | 1.5 or 2.5 | yes       |
| BTTS            | YES, NO             | none       | yes       |
| Double Chance   | 1X, X2, 12          | none       | no        |
| Home Team Total | OVER, UNDER         | 0.5 or 1.5 | yes       |
| Away Team Total | OVER, UNDER         | 0.5 or 1.5 | yes       |

Missing required selections produce INCOMPLETE_MARKET. Existing prices retain their odds and raw implied probabilities, while book percentage, overround, and no-vig probabilities remain unavailable. Missing selections are never fabricated.

Lines use Decimal numeric equality, so 2.5, 2.50, and 2.500 are equivalent. Wrong or absent required lines and forbidden lines are rejected.

## Double Chance

Double-chance selections overlap and must not be normalized as a mutually exclusive three-way market. 1X, X2, and 12 each contain two underlying match outcomes, so summing all three raw probabilities is not a conventional three-way book percentage.

TASK 11 returns NON_EXCLUSIVE_MARKET for a Double Chance group. It does not produce conventional group book percentage, overround, or proportional no-vig probabilities across those three selections. Each individual decimal price and raw implied probability remains valid and auditable.

## Market grouping

One immutable MarketGroup represents one match, provider/bookmaker source, canonical market, exact line, and reference semantic. Every price must match those fields. Mixed matches, providers, markets, lines, or reference semantics are rejected. Duplicate selections are rejected without choosing first, latest, best, maximum, or average.

Incoming collections are copied to tuples and never mutated. Results use registry-defined selection ordering, independent of input order.

Provider identifiers are generic provenance only. There is no Bet365, Pinnacle, William Hill, Betfair, football-data.co.uk, or other operator-specific rule. In particular, source-specific historical Pinnacle handling is deferred to TASK 12.

Caller-supplied observed_at timestamps must be timezone-aware and are preserved. No timestamp is generated, and opening or closing status is not inferred.

## Reference-price semantics

The price contract can explicitly represent:

- SOURCE_PRICE: one provider observation.
- REFERENCE_MARKET: a price designated by a future evaluation policy.
- BEST_AVAILABLE: a future cross-provider best-price result.
- CONSENSUS: a future multi-provider consensus result.
- OPENING: a future source-history opening observation.
- CLOSING: a future source-history closing observation.

These values are semantically distinct. Best available, consensus, opening, closing, and reference-market values are representable contracts only; TASK 11 does not calculate or infer them. Best price is not assumed to be reference, consensus is not assumed to be reference, and closing is not assumed to be reference.

TASK 11 performs no bookmaker aggregation: no mean, median, min, max, line shopping, bookmaker ranking, consensus construction, or sharp-book weighting.

## Diagnostics

Configurable provisional thresholds can identify suspiciously high positive overround or material underround. Diagnostics are informational. They neither reject otherwise valid complete markets nor change source odds, raw probabilities, overround, or normalized mathematics.

## Numeric precision and auditability

Odds, probabilities, book percentage, overround, thresholds, and tolerances use Decimal. Local calculation contexts avoid changing process-global Decimal behavior. Results serialize Decimals as strings, enums by stable values, datetimes as ISO strings, and selections in canonical registry order.

Contracts and configuration are frozen. Identical inputs and configuration yield identical output without current time, randomness, environment settings, filesystem input, network access, database state, or mutable caches.

## Boundaries and deferred work

TASK 11 has no database or SQLAlchemy dependency; no migration or persistence exists. It imports no Poisson, Elo, Form, ML, signal/agreement, edge, Bet Score, or publication implementation. It does not compute model comparison, edge, expected value, Kelly staking, settlement, picks, or recommendations.

TASK 11 does not select bookmakers and does not compute betting value. It contains no sportsbook referral, affiliate, bonus-code, redirect, acquisition tracking, or Bet Now behavior.

Deferred work includes historical odds normalization, source-specific quality policy, bookmaker aggregation, best-price calculation, consensus construction, opening/closing derivation, alternative vig-removal implementations, TASK 12, TASK 13, edge, expected value, calibration, publication integration, persistence, and API exposure.

This foundation proves only deterministic market-price mathematics and semantics. It makes no claim about profitability, predictive accuracy, recommendation quality, or production validation.
