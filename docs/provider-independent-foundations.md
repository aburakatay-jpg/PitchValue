# Provider-independent safe foundations

This package extends the completed PitchValue backend with provider-neutral operational and
evidence contracts while both commercial provider gates remain pending. It does not select,
integrate, or encode Sportmonks or The Odds API behavior. No scheduler, notification service,
archive service, Supabase deployment, shadow run, or public PICK is activated.

## Schema reviews

### Operational audit

Before this package the database had no durable entity for a run, quarantine, operational event,
or consumer delivery state. Logs, Telegram, and Drive cannot be canonical audit history. Migration
`20260912_0009` therefore adds `engine_runs`, `run_quarantines`, `operational_events`, and
`operational_event_deliveries`. IDs are caller-supplied deterministic identities; event content is
immutable and delivery status is consumer-specific and retryable. Foreign-key deletion is
restrictive. Downgrade removes the four new empty/provider-neutral tables in dependency order.

### Versioned DQ evidence

The legacy `data_quality` table is a one-row-per-match ingestion summary. It cannot represent
multiple evaluations, profile/version identity, evidence-family availability, observed time, or
provenance. Migration `20260912_0010` adds `data_quality_evaluations` and
`data_quality_evidence` without modifying or backfilling the 4,460 legacy rows. Evaluation identity
is deterministic across match, evaluation time, profile, and version. Downgrade removes only the
new empty/provider-neutral evidence tables. Numeric `quality_score` remains nullable and this
package never calculates or populates it.

No `prediction_snapshots` column was added: run linkage and shadow persistence need a separate
future decision after actual generation workflow requirements are known. This avoids speculative
schema coupling.

## Operational runs and schedule representation

`EngineRun` preserves run type, scheduled/started/finished timestamps, lifecycle, local fixture
horizon, all engine/evidence versions, and a provider-contract placeholder. The lifecycle is
explicit and terminal; a retry is a new caller-controlled run identity. `persist_run` is
idempotent. Nothing starts a daemon.

The schedule contract contains Tuesday 08:00 UTC for Tuesday–Thursday and Friday 08:00 UTC for
Friday–Monday. Fixture membership uses `zoneinfo` local dates rather than blind UTC dates and is
tested across midnight, Europe DST, and kickoff revisions.

## Quarantine and events

MATCH quarantine blocks a whole match. MARKET_FAMILY quarantine includes the family identity, so
healthy independent families remain usable. Quarantine identity is deterministic by run, match,
scope, family, and reason.

Operational events have stable types, reason codes, canonical severity, correlation IDs, component
identity, provider-domain placeholder, and secret-free metadata. Event replay does not create a new
logical event. Delivery status is stored separately for each consumer; notification or archive
failure cannot change prediction state.

## DQ evidence

The six families are historical depth, match-statistics completeness, current-season freshness,
fixture integrity, entity mapping integrity, and source/provider health. States are AVAILABLE,
PARTIAL, UNAVAILABLE, and HARD_FAIL. Missing does not become zero. Hard failure is independent of
any future numeric score and cannot be overridden by one.

`HISTORICAL_RECONSTRUCTED` cannot claim live current-season freshness or live provider health.
`LIVE_OPERATIONAL` remains a separate profile. No final weights, thresholds, or DQ score exist.

## Market stability evidence

Comparable observations must share match, bookmaker, market, selection, Decimal line, and
normalization version. The calculator reports count, observation bounds, absolute and maximum-step
implied-probability movement, reversal count, maximum gap, completeness, continuity, and freshness.
It rejects incomplete, future, duplicate-time, or mixed-identity series.

Exactly one observation can establish existence, completeness, and freshness but returns
`MARKET_STABILITY = UNAVAILABLE`; no numeric stability score exists.

## Calibration-confidence research

The research selector reuses TASK 14 reliability buckets, support counts, calibration gaps, and
ECE-like metrics. An explicit fallback hierarchy may move from recent competition evidence to
broader same-market evidence. It cannot cross market or model version. There is no frozen minimum
sample size or numeric confidence mapping. RAW ML probabilities are unchanged, rejected
temperature scaling remains rejected, and absent market-specific OOS evidence returns UNAVAILABLE.

## External consumer boundaries

Telegram and Drive are protocols plus deterministic fake adapters only. Telegram groups operational
events. Drive archives an immutable report package by run ID. Both return retryable failure status
without changing predictions. No credentials or network calls exist; the database remains canonical.

Supabase work is staging-readiness tooling only. It distinguishes direct, session, and transaction
pooling, requires direct migration access and TLS, and identifies prepared-statement/session-state
risks. Production is not deployed.

## Mobile and shadow boundaries

Mobile state contracts cover LOADING, API_UNAVAILABLE, EMPTY, DATA_INSUFFICIENT, NO_BET,
WATCHLIST, PICK, SCORE_INCOMPLETE, CHANGED, HISTORICAL, and STALE for Today, Explore, Match Detail,
My Bets, and Premium surfaces. They contain no client-side probability, no-vig, edge, Bet Score, or
publication math. Internal shadow PICK can be represented while public PICK requires
`MODEL_READINESS_GATE = PASS`.

The shadow contract is immutable, provider-neutral, timestamp-honest, and always
non-publication-eligible. It preserves nullable odds, evidence references, closing reference,
result, and settlement status. No shadow run or settlement calculation occurs.

## Unresolved gates

- Sportmonks and The Odds API field meanings, IDs, cadence, coverage, licensing, storage rights,
  and SLA remain unknown and unimplemented.
- Final DQ weights/threshold, Market Stability score, Calibration Confidence score, and live-shadow
  PASS threshold require main architecture decisions.
- Public PICK remains disabled until `MODEL_READINESS_GATE = PASS`.
- Multi-market production implementation remains deferred; see `docs/v1-market-code-audit.md` for
  actual-code classifications and a non-frozen recommended order.
