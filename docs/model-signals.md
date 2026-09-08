# Model signals and agreement

TASK 10 provides a small orchestration boundary between independent model outputs and future ensemble/publication work. It answers which canonical selection each usable model explicitly supports and how those models align. Agreement is not an ensemble probability and is not a publication decision.

The layer is pure and deterministic:

Poisson / Elo / Form output → signal adapter → shared ModelSignal → agreement result

It does not invoke model computation, mutate model outputs, query a database, read odds, calculate edge or Bet Score, blend probabilities, or call publication policy.

## Shared signal contract

Each signal identifies its model family, version/name, match, canonical TASK 05 market, optional explicit selection, directional preference, status, normalized strength, optional probability, raw source value, and compact diagnostics.

Model families have a fixed audit order:

1. POISSON
2. ELO
3. FORM
4. ML

ML is a contract reservation only; no ML model exists.

Signal states include READY, INPUT_INSUFFICIENT, ANALYSIS_UNAVAILABLE, INVALID, UNSUPPORTED_MARKET, and AMBIGUOUS. Only READY signals enter the usable denominator. Unavailable, invalid, unsupported, and ambiguous outputs never become neutral evidence or agreement.

normalized_strength is a bounded 0–1 comparative strength. It is not necessarily a probability. A separate optional probability field exists only when a model actually produces one.

## Poisson adapter

Poisson market probabilities retain their raw probability mass. The adapter chooses the highest probability for the requested canonical market/line and uses that probability as both probability and the transparent normalized strength. It never renormalizes truncated 1X2 mass.

For match result, represented probability mass is checked against the configured residual tolerance. Excess residual produces ANALYSIS_UNAVAILABLE. A top-two difference at or below the ambiguity tolerance produces AMBIGUOUS, with no arbitrary enum-order winner.

The default ambiguity and residual thresholds are provisional and subject to backtest calibration.

## Elo directional adapter

**INITIAL ELO SIGNAL THRESHOLDS — SUBJECT TO BACKTEST CALIBRATION.**

Elo supports only directional match-result evidence:

- expected home score at or above 0.55 → HOME
- expected home score at or below 0.45 → AWAY
- between those bounds → NEUTRAL

Normalized strength is abs(expected_home_score - 0.5) × 2. Elo expected score remains a rating-update strength expectation; it is not exposed as a football home-win probability.

## Form directional adapter

**INITIAL FORM SIGNAL THRESHOLDS — SUBJECT TO BACKTEST CALIBRATION.**

Form also supports only directional match-result evidence:

- relative form signal at or above +0.10 → HOME
- relative form signal at or below -0.10 → AWAY
- between those bounds → NEUTRAL

Normalized strength is the absolute TASK 09 relative signal. No probability is fabricated.

## Neutral and draw semantics

NEUTRAL means a directional model did not cross its minimum directional threshold. It does not mean DRAW.

Only a model that explicitly selects DRAW supports a draw candidate. Therefore Poisson DRAW plus neutral Elo and Form yields one draw supporter, not three. A future ML signal may explicitly support draw through the shared contract, but TASK 10 implements no ML model.

## Agreement denominators

For a requested candidate selection:

- supporting_model_count counts READY signals explicitly selecting that candidate.
- usable_model_count counts all READY signals, including neutral and conflicting signals.
- configured_model_count is the planned configured ensemble size.
- usable_agreement_ratio is support divided by usable models and is absent when none are usable.
- configured_agreement_ratio is support divided by all configured model families.

The default configuration contains Poisson, Elo, Form, and future ML. With three currently implemented models all supporting home and ML absent:

- usable agreement is 3/3 = 1.00
- configured agreement is 3/4 = 0.75

This preserves the TASK 05 planned 3/4 semantics. A ready three-model runtime decision does not silently redefine the planned denominator.

Agreement also exposes canonical-order buckets:

- agreeing models explicitly select the candidate;
- conflicting models are ready and explicitly select another selection;
- neutral models are ready but directionally neutral;
- unavailable models include missing, insufficient, invalid, unsupported, or ambiguous families.

The configured minimum usable model count determines whether the agreement calculation has enough runtime evidence. This is separate from whether the configured agreement ratio meets its future compatibility threshold, and neither field is publication eligibility.

## Market support

Poisson can adapt any V1 market/line present in its TASK 08 output. Elo and Form support only match_result direction in TASK 10. Requests such as Elo BTTS or Form total goals produce UNSUPPORTED_MARKET and do not count as usable.

The match-result helper evaluates candidates in stable HOME, DRAW, AWAY order. Input ordering cannot change output ordering or model buckets.

## Configuration and numeric handling

Configuration is immutable and uses decimal fractions:

- required agreement ratio: 0.75, never 75;
- Elo thresholds: 0.45 and 0.55;
- Form thresholds: -0.10 and +0.10;
- Poisson ambiguity and residual tolerances;
- minimum usable models: 3;
- canonical configured families.

Validation rejects duplicate or noncanonically ordered families, impossible usable counts, out-of-range ratios/tolerances, and asymmetric directional bands. Signals reject non-finite or out-of-range strengths and probabilities. Decimal values serialize as strings for stable audits.

## Explicitly deferred

TASK 10 does not implement ML, empirical calibration, weighted blending, combined probability, edge, Bet Score, odds integration, publication decisions, historical backtesting, API exposure, or persistence. Those require later tasks and, for empirical work, historical data.
