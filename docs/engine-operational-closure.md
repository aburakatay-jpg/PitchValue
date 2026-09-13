# Engine operational closure

This closure keeps the zero-cost shadow engine provider-independent, fail-closed, and disabled
until an operator deliberately activates it. The engine foundation is complete for the current
shadow objective; this document does not authorize public predictions or scheduler execution.

## Fixture lifecycle

The canonical lifecycle contract can represent `SCHEDULED`, `IN_PLAY`, `FINISHED`, `AWARDED`,
`POSTPONED`, `CANCELLED`, and `ABANDONED`. Its transition matrix accepts only explicit forward
movement, permits a postponed fixture to return to scheduled, and sends contradictory terminal
transitions or corrected final results to review. Kickoff changes preserve fixture/provider
identity only while scheduled or postponed. Non-playable states cannot enter model execution.

That capability is deliberately separate from the 5DFA runtime mapping. The verified Free payload
maps only scheduled, in-play, and finished. An unknown source status is retained as source evidence,
quarantined as `UNKNOWN_LIFECYCLE_REVIEW`, and is not invented as postponed, cancelled, or
abandoned. Because the current canonical match schema has no in-play value, in-play source evidence
is not promoted to a new canonical state and remains barred from prediction eligibility.

## Run, locking, and recovery

Manual execution uses one canonical service and exposes run identity, provider, bounded window,
prediction cutoff, source sync/refresh, eligibility and quarantine totals, model evidence,
persistence stages, report path, and terminal status through durable runs/events and local reports.
Success is terminal only after all required persistence and report stages succeed.

PostgreSQL session advisory locks protect a deterministic semantic run identity. Concurrent replay
of the same identity is rejected while independent scopes may proceed. Locks are released in a
`finally` path and by PostgreSQL on lost sessions. Stale `RUNNING` records are detected without
rewriting history. `recover-stale` first checks age and the live lock, then marks only a genuinely
stale run failed, persists an audit event, and never retries provider work automatically.

## Scheduler and heartbeat

Scheduler state is `DISABLED_READY_FOR_ACTIVATION`. No scheduler is installed or running. The
canonical future schedule is Tuesday 08:00 UTC for Tuesday–Thursday fixture-local dates and Friday
08:00 UTC for Friday–Monday fixture-local dates. UTC triggers, fixture-local date membership, DST,
bounded windows, deterministic identities, duplicate protection, missed runs, stuck runs, and
failed/partial prior runs are covered independently of any scheduler framework.

Health means the process/database foundation is available. Readiness means the canonical shadow
run can execute: current migration, model contracts, provider configuration when required,
persistence repositories, canonical mappings, and writable report storage. Exact odds timestamps,
Market Stability, and Final Check are evidence limitations and are not fabricated readiness
requirements. Heartbeat separately reports missing starts, stale running work, failures, partial
runs, current-season freshness, fixture-refresh freshness, and report failure.

## Provider, quota, and coverage

Only idempotent GET requests may retry. Timeout, connection failure, rate limit, and transient 5xx
responses use bounded deterministic backoff; `Retry-After` is respected. Authentication, permanent
4xx, plan, and malformed-payload errors do not retry. Known quota must cover the preflight estimate;
unknown quota permits only the conservative bounded call budget. There is no paid quota assumption.

Authenticated Free-plan runtime evidence currently marks Premier League, Ligue 1, Bundesliga, and
La Liga `AVAILABLE`. Süper Lig, Primeira Liga, Scottish Premiership, UEFA Champions League, UEFA
Europa League, and UEFA Conference League are `NOT_YET_VERIFIED`. None is declared unavailable
without source evidence. Serie A remains out of PitchValue V1 scope.

## Evidence, reporting, and alerts

Local archives contain `run-summary.json`, `fixtures.csv`, `predictions.csv`,
`market-evaluations.csv`, `data-quality.csv`, `quarantined-matches.csv`, and `errors.json`. Files are
deterministic and secret-free. Required archive failure prevents a success claim but never deletes
already persisted audit evidence.

Operational events use the durable outbox state before delivery. The current implementation is
`FAKE_ADAPTER_ONLY`: no Telegram credentials are configured and no paid alert service is used.
Delivery failure is visible and retryable where classified, but cannot invalidate valid engine
evidence. Google Drive remains deferred.

The accumulated real shadow evidence remains internal and replay-safe. The accepted 11-fixture
window produced RAW ML and Elo for 11/11 and Form/Poisson for 10/11. Getafe–Malaga is an expected
provider-independent limitation: Malaga had no canonical pre-cutoff match history, so Form and
Poisson correctly stayed unavailable. Across all 14 durable shadow rows, RAW ML/Elo are present on
14, Form is ready on 12, Poisson is ready on 11, and agreement evidence is present on 14. The
Poisson residual tolerance remains `0.001`.

Odds remain `MARKET_REFERENCE_ONLY`. `TIMESTAMP_GATE = PENDING`,
`MARKET_STABILITY = UNAVAILABLE`, and `FINAL_CHECK_UNAVAILABLE`. Request, ingestion, database, and
local clock time are never substituted for market observation time. Shadow analysis is never a
public prediction; publication eligibility remains false and public reads fail closed.

## Release validation and operator commands

`python -m pitchvalue.operations.release_validation` performs the minimal read-only schema check.
The expanded shadow activation validator checks database/migration, provider configuration, model
contracts, canonical mappings, shadow repositories, report path, current-season freshness,
activation gates, and public isolation without calling the provider.

`python -m pitchvalue.operations.status status` reports secret-safe health, readiness, provider
configuration, quota knowledge, activation gates, heartbeat, recent runs, stuck work, critical
events, and public counts. `inspect <run_id>` reports run lifecycle, scope, versions, quarantines,
model coverage, events, and report-location availability. `recover-stale <run_id>` is the explicit
audited recovery path.

Activation gates are fail-closed. Missing values mean false. The required current state is
`SCHEDULER_ENABLED=false`, `PUBLICATION_ENABLED=false`, and `EXTERNAL_ALERTS_ENABLED=false`.

Backend contract audit:

- Explore/public-eligible list and per-match public predictions exist and may safely be empty.
- `BACKEND_CONTRACT_GAP`: canonical Today fixture list.
- `BACKEND_CONTRACT_GAP`: Match Detail fixture/result/statistics response.
- `BACKEND_CONTRACT_GAP`: public supported-market and data-insufficient state schema.
- `BACKEND_CONTRACT_GAP`: explicit stale and Final Check response state.
- Fixture visibility must not depend on a public pick; shadow rows never fill Explore.

## Rollback and incidents

Rollback first disables scheduler, publication, and external alerts, then stops provider
execution. It preserves runs, quarantines, events, outbox deliveries, source evidence, and shadow
rows. Application rollback uses a reviewed code revision. Migration rollback requires a separate
nondestructive review; deleting evidence is never a rollback strategy.

Provider outage or timeout degrades/stops safely; revoked authentication and permanent payload
errors fail the run; exhausted/unknown quota blocks an unsafe scan; malformed payload is not
retried; database or core persistence failure is systemic; a stuck run requires inspected recovery;
a missed run is heartbeat-visible; report failure prevents successful terminal status; delivery
failure remains in the outbox; and uncertain publication evidence returns nothing public. The safe
choices are stop, degrade, or quarantine—never fabricate.
