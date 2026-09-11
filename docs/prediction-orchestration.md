# Prediction orchestration

TASK 20 combines existing model, signal, data-quality, market, scoring, and policy
contracts into a deterministic decision record. It does not acquire live data, write
predictions, or publish recommendations.

## Evidence ownership

RAW TASK 16 ML remains the canonical probability source. The TASK 17 calibration
candidate and TASK 18 ensemble candidate were rejected and are not orchestration
inputs. Poisson, Elo, and Form remain TASK 10 signals; Elo and Form are not treated as
probabilities, and NEUTRAL is not DRAW.

TASK 19 supplies the Decimal odds, no-vig market probability, edge, observation role,
timing semantics, market quality, and lineage. TASK 20 does not recalculate edge or
no-vig probability. Canonical edge remains model probability minus no-vig market
probability.

## Bet Score and evidence completeness

The TASK 05 policy remains the sole scoring authority. Its configured weights are:

- Edge: 35%
- Model agreement: 25%
- Data quality: 15%
- Calibration confidence: 15%
- Market stability: 10%

TASK 05 already defines edge-score interpolation, configured-model agreement scoring,
the weighted formula, and score classes. It accepts explicit data-quality, calibration,
and stability scores, but the repository does not define evidence-to-score mappings for
calibration or stability. TASK 20 does not create such mappings.

Unavailable policy components are not assigned invented scores.

Missing weights are not redistributed and
the five configured weights continue to total 1.00. Bet Score completeness is reported
as COMPLETE, PARTIAL, or UNAVAILABLE, and a partial score is not calculated.

RAW ML is uncalibrated because the TASK 17 candidate was rejected. Consequently the
calibration component is unavailable unless a future caller supplies evidence under an
approved scoring contract. The TASK 18 fold evidence may be carried as diagnostics, but
it is not converted into an arbitrary stability score.

## Independent gates

Each selection exposes these gates separately:

- EDGE_GATE: edge must be at least 0.06.
- BET_SCORE_GATE: a complete Bet Score must be at least 70.
- AGREEMENT_GATE: TASK 10 must report sufficient usable evidence and at least three of
  four configured families supporting the selection.
- DATA_QUALITY_GATE: the existing TASK 05 minimum score is 70.
- MARKET_TEMPORAL_GATE: exact observed-at evidence must be at or before prediction_as_of.
- MARKET_QUALITY_GATE: market quality must be eligible.
- COMPONENT_COMPLETENESS_GATE: every weighted score component must be available.
- ODDS_PRESENTATION_GATE: the existing TASK 05 presentation policy is preserved.

Edge >= 6% alone does not produce a Pick.

A Pick requires all mandatory policy gates to pass.

The configured edge ranges remain below 4%, 4% to below 6%, and at least 6%. Bet Score
classes remain below 60 NO BET, 60–69 WATCHLIST, 70–79 PICK, 80–89 STRONG, and 90+
ELITE. Odds below 1.35 remain hidden by presentation policy, the exceptional low-odds
rules remain configured in TASK 05, 1.50–2.20 remains ideal, 2.21–3.00 remains higher
risk, and odds above 3.00 cannot be a main V1 pick. These rules do not alter probability,
no-vig, or edge math. No threshold was tuned from TASK 20 output.

## Decision precedence and ambiguity

Invalid or unavailable core evidence is blocked. Edge below 4% produces NO BET; the
4%–below-6% range is WATCHLIST at most. At or above 6%, every other policy gate must
pass before PICK, STRONG, or ELITE can be returned. A high Bet Score cannot override a
failed edge, agreement, data-quality, quality, completeness, or odds-policy gate.

NO BET is a valid deterministic engine outcome.

Selections are evaluated independently. The TASK 19 best-edge selection is diagnostic
and has no bypass. If more than one selection is a provisional policy candidate and no
canonical tie-break exists, the match result is MULTIPLE_POLICY_CANDIDATES with no
selected candidate.

## Historical simulation versus publication

Historical ROLE_ONLY_COMPARISON market evidence is not publication-eligible production evidence.

The source-prematch run is labeled ROLE_ONLY HISTORICAL POLICY SIMULATION. The closing
run is labeled CLOSING REFERENCE POLICY DIAGNOSTIC. In both cases the market role is
known but its exact observation timestamp is not. Neither prediction_as_of, ingestion
time, staging time, file time, nor runtime time is substituted for observed_at. A
historical simulated policy class is separate from production publication eligibility.

Future live observations can use the same engine when timing semantics are exact,
observed_at is timezone-aware and no later than prediction_as_of, quality is eligible,
and all other policy evidence is complete. TASK 20 adds no live provider integration.

## Auditability and boundaries

Immutable selection results preserve match and selection identity, RAW ML version and
probability, model-signal statuses, both TASK 10 agreement denominators, data-quality
evidence, market role/timing/quality, TASK 19 lineage, component status and weight,
Bet Score completeness, every gate, deterministic blockers, policy decision,
publication eligibility, and semantic versions.

TASK 20 does not calculate realized ROI or Kelly staking.

It also does not fit calibration, accept an ensemble, settle bets, use an LLM for any
decision, persist results, expose an API, or issue production recommendations from
role-only historical prices.
