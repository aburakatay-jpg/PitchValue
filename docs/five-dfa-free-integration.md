# 5DollarFootballAPI Free integration

This package is an initial, non-public provider adapter for the 5DollarFootballAPI **FREE** plan.
It does not activate scheduled execution, make live requests during tests, write live predictions,
or enable public PICK. The Odds API is not integrated.

## Verified Free boundary

The capability contract is versioned as `five_dfa_free_capabilities_v1`. PitchValue enables only
Premier League, Ligue 1, Bundesliga, and La Liga even though the provider also lists Serie A in its
Free coverage. The supported bookmaker set is exactly Bet365. Free quota metadata is 60 requests
per hour with a 20-request-per-minute burst ceiling, and history is represented as the last three
months. Batch fixture-list odds and odds tick history are unavailable.

PitchValue's initial normalized markets are narrower than the complete provider catalogue:

- MATCH_RESULT: HOME, DRAW, AWAY
- BTTS: YES, NO
- TOTAL_GOALS: OVER/UNDER only when the actual line is exactly Decimal `1.5` or `2.5`

Asian handicap, corner/card markets, half-time markets, Double Chance, and team totals are not
normalized. A returned goal line of 2.75 is retained as an unsupported-line diagnostic and is not
changed into 2.5.

## Client and quota behavior

The adapter uses the documented Bearer header, bounded timeout, sequential pagination, and the
Free-compatible per-fixture Bet365 odds endpoint. It does not use paid list-level odds expansion.
Valid empty results are distinct from authentication, plan, rate-limit, provider, timeout, and
payload failures. `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`,
and request IDs are retained when present. A safe GET may retry once only when configured.

No API key is required for normal PitchValue startup. `FIVEDFA_API_KEY` is loaded only when this
adapter is explicitly constructed, is never shown in `repr`, and tests use fake values and mocked
HTTP responses.

## Mapping and fixture refresh

Provider competition, team, and fixture IDs are source references, never canonical PitchValue
identities. Competition IDs are accepted as opaque IDs from runtime/documented payloads rather
than hard-coded from memory. Team resolution requires an explicit source-ID mapping and never
uses fuzzy fallback.

The current-season refresh planner detects new fixtures, exact-identity reuse, changed kickoff,
finished transition, duplicate rows, unsupported competition, missing score, unresolved teams,
and unknown status. `finished` is the only final-result state. `unknown` is retained for review and
is never synthesized into postponed or cancelled. A replacement provider fixture ID is reconciled
only when competition, canonical teams, and kickoff match exactly; otherwise it is quarantined for
review. The planner is deterministic and does not write to the real database in this task.

Basic statistics normalize only explicitly returned shots-on-target, possession, corner, and card
fields. Missing is `None`; a returned zero remains zero. Rich statistics are not inferred.

## Time, stability, and publication safety

Provider timestamp-like fields are preserved by their source names as evidence. Their semantics
are not promoted to canonical `market_observed_at` without a separately verified contract.
Database insertion time, request time, ingestion time, and schedule time are never substituted.

`TIMESTAMP_GATE = PENDING`

Opening and closing snapshot labels are preserved as roles with `ROLE_ONLY` timing and
`observed_at = None`. Consequently they are not publication-safe price evidence.

Free has no odds tick-history capability. One snapshot cannot establish stability.

`MARKET_STABILITY = UNAVAILABLE`

Free does not supply confirmed lineups or injury/suspension evidence:

- `FINAL_CHECK_UNAVAILABLE`
- `INJURY_EVIDENCE = UNAVAILABLE`

Capability absence degrades only the dependent component or affected match/market family. It does
not fabricate inputs or crash an otherwise valid run. No odds means no market probability/edge;
an unsupported market is unavailable; an unresolved fixture mapping is quarantined.

## Operational status

All integration tests are mocked. No live credential was available or required, no live provider
request was made, no scheduler was activated, and no production/historical row was modified.
Public PICK remains disabled until `MODEL_READINESS_GATE = PASS` and every existing publication
gate is satisfied.

If Free-plan data is displayed publicly later, the provider's current attribution terms must be
implemented during the separate public-product integration review.
