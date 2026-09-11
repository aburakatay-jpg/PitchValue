# Prediction API

TASK 22 exposes the current prediction cache through the existing FastAPI `/api/v1` namespace.
Prediction API responses are served from persisted prediction snapshots and do not trigger model recomputation.
Routes call the TASK 21 repository and map its immutable read records into an explicit public schema;
they do not execute ML, edge, scoring, or policy code.

## Endpoints

- `GET /api/v1/matches/{match_id}/predictions` returns current publication-eligible rows for one
  match. A missing match or a match without published predictions returns an empty collection.
- `GET /api/v1/predictions` returns a bounded current publication cache. Repeated `match_id` query
  parameters can constrain the call to a fixture set. `limit` defaults to 100 and is capped at 100;
  `offset` supports deterministic paging.

Both endpoints order results by match, market, and selection after TASK 21 selects the current active
version by `prediction_as_of`, then `generated_at`.
Invalidated and superseded prediction snapshots are excluded from current public reads. The API does
not implement its own latest-version algorithm.

## Publication and temporal safety

Public prediction endpoints do not promote non-publication-eligible records. Filtering is performed
by the persistence repository using the stored `publication_eligible` and active status; API code
does not rerun policy gates. Historical ROLE_ONLY_COMPARISON records are not exposed as production picks.
Missing `market_observed_at` remains null and is never replaced with prediction, generation,
persistence, staging, import, or request time.

## Response contract

Public responses include match/market/selection identity, the persisted RAW ML probability source,
model probability, prediction and generation times, price, no-vig market probability, edge, safe
market timing fields, stored decision, score class, nullable Bet Score, completeness, public component
availability, blockers, and consumer-relevant versions. Nullable Bet Score values remain null in the API response.

Decimal fields retain Pydantic Decimal serialization and timezone-aware timestamps use ISO 8601.
Enums and blocker codes use stable string values. The public schema excludes database primary keys,
payload hashes, source staging IDs, provider-reference IDs, and invalidation metadata. Full lineage
and audit history remain available only inside the repository.

## Access and product boundary

The current backend has no authentication or authorization layer, so these read endpoints preserve
the existing unauthenticated architecture. TASK 22 does not invent subscription or premium
entitlements. A future product layer may control visibility of the one canonical persisted prediction;
it must not create per-user prediction calculations.

An empty `prediction_snapshots` table is a valid state and returns a successful empty response.
Prediction endpoints expose no POST, PUT, PATCH, or DELETE operation. TASK 22 does not integrate a live data provider.
It adds no Redis cache, refresh job, provider credential, mobile change, LLM explanation, settlement,
or prediction write. TASK 23 owns final operational safeguards and end-to-end release validation.
