# Public fixture and match-detail API

The V1 fixture contracts are additive, read-only projections over canonical persistence. They do
not execute models, fetch providers, or read internal shadow analysis.

## Today

`GET /api/v1/fixtures/today` returns fixtures ordered by canonical kickoff time. `date=YYYY-MM-DD`
is optional and `timezone` defaults to `Europe/Istanbul`; timezone conversion uses IANA rules. A
fixture remains visible when no public prediction exists.

Top-level states are `FIXTURES_AVAILABLE`, `NO_FIXTURES`, `STALE_FIXTURE_DATA`, and
`PROVIDER_UNAVAILABLE`. Fixture data availability is distinct from public analysis availability.
No fixtures is a successful empty collection, not a server error.

## Match Detail

`GET /api/v1/matches/{match_id}` returns canonical competition, kickoff, teams, lifecycle, a final
score only when stored, a supported statistics subset only when present, freshness metadata, public
prediction state, nine V1 market-state entries, and Final Check state. Missing statistics use the
normal domain state `DATA_INSUFFICIENT` with a null statistics object.

No public prediction produces `NO_PUBLIC_ANALYSIS`; it does not produce a synthetic `NO_BET`.
Nullable Bet Score remains null. `SCORE_INCOMPLETE` and completeness metadata preserve that absence
without substituting zero.

## Market, publication, and Final Check states

The market-state vocabulary is `AVAILABLE_PUBLIC`, `ANALYSIS_UNAVAILABLE`, `DATA_INSUFFICIENT`,
`SCORE_INCOMPLETE`, `NOT_SUPPORTED`, and `NOT_PUBLISHED`. The response lists 1X2, O/U 1.5,
O/U 2.5, BTTS, Double Chance, and home/away team-goal O/U 0.5 and 1.5 independently. A state never
creates a probability, edge, price, or score.

Publication and Final Check are separate. Publication states can represent `PICK`, `WATCHLIST`,
`NO_BET`, `DATA_INSUFFICIENT`, or `NO_PUBLIC_ANALYSIS`. Final Check states are `CONFIRMED`,
`CHANGED`, `WITHDRAWN`, and `FINAL_CHECK_UNAVAILABLE`. Current 5DFA Free evidence always returns
`FINAL_CHECK_UNAVAILABLE`; the backend never synthesizes confirmation.

## Freshness and errors

Freshness derives only from durable `FIXTURE_REFRESH_*` events and fixture-source
`last_seen_at` evidence. Response time, request time, database read time, and local clock time are
not source freshness. Successful refresh, failed refresh, stale evidence, and unavailable evidence
remain distinct. A fixture response can therefore succeed while its analysis, statistics, or Final
Check subsection is unavailable.

Missing fixture identity returns the existing safe `NOT_FOUND` envelope. Invalid query input uses
`VALIDATION_ERROR`. Provider unavailability is a domain availability state when canonical fixture
data can still be served; raw provider errors and stack traces are never exposed.

## Public isolation

Shadow/internal evidence is never a public fallback. Today and Match Detail query only canonical
fixture/statistics data and publication-eligible current prediction snapshots. They never query
`shadow_analysis_snapshots`. Explore remains `GET /api/v1/predictions` and an empty result is valid.
Role-only odds remain `MARKET_REFERENCE_ONLY`, `TIMESTAMP_GATE = PENDING`, and cannot become a
public edge through these contracts.

Report archive paths for future persisted shadow runs are stored in the existing
`REPORT_GENERATION_SUCCEEDED` event metadata. Legacy paths remain explicitly unavailable unless an
operator supplies `PITCHVALUE_REPORT_DIRECTORY`, in which case year/run identity resolves the
deterministic expected location. No migration is required.

These endpoints do not activate scheduler, publication, authentication, payment, or UX behavior.
