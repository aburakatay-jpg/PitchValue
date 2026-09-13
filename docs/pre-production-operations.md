# Pre-production engine operations

This checkpoint prepares the manual shadow engine for a future scheduler without enabling one.
The canonical execution sequence is readiness, quota preflight, PostgreSQL advisory lock,
execution, transactional persistence, report generation, terminal status, and lock release.
`SCHEDULER_ENABLED`, `PUBLICATION_ENABLED`, and `EXTERNAL_ALERTS_ENABLED` are independent,
strict boolean gates. Missing values mean disabled. Current intended values are all `false`.

## Concurrency and recovery

The lock key is a stable signed 64-bit digest of the complete semantic run identity and
`postgres_advisory_run_lock_v1`. A PostgreSQL session advisory lock prevents a concurrent manual
or future scheduled worker from executing the same run. Independent identities may proceed. The
lock is released in a `finally` path, including exceptions; PostgreSQL also releases it if the
session terminates.

`python -m pitchvalue.operations.status status` reports readiness, activation gates, recent runs,
stale RUNNING records, recent error events, and public eligible counts without printing secrets.
`inspect <run_id>` shows persisted lifecycle evidence. A stale record can be changed to FAILED only
with the explicit `recover-stale <run_id> --older-than-minutes N` command. Recovery first verifies
the age boundary and that the advisory lock is not active, preserves the run, and adds an audited
RUN_FAILED event. It never retries provider work automatically.

## Provider and failure safety

Only idempotent GET operations may retry. Timeouts, connection failures, bounded 5xx responses,
and a 429 with a usable Retry-After may retry once. Authentication, plan, malformed payload, and
permanent 4xx failures do not retry. Backoff is deterministic and capped at ten seconds; a larger
Retry-After is returned to the operator instead of sleeping early and violating it. Before fixture
odds expansion, known remaining quota must cover the conservative maximum call count. When quota
headers are absent, no more than eight additional calls are permitted.

Failures are classified as SYSTEMIC, FIXTURE_LOCAL, MARKET_FAMILY_LOCAL, PROVIDER_TRANSIENT,
PROVIDER_PERMANENT, CONFIGURATION, PERSISTENCE, or REPORTING. Fixture and market-family failures
remain local. Infrastructure, authentication, configuration, and persistence failures fail the
run. Fixture/source persistence and analysis evidence use explicit transactions. A reporting
failure cannot emit success and leaves prior auditable persistence attached to a FAILED run.

## Health, readiness, and public safety

Process liveness remains `/health`. Manual engine readiness separately checks PostgreSQL, exact
Alembic head, shadow persistence schema, model contract loading, and provider configuration when a
provider run is requested. Exact odds time, Market Stability, and Final Check are evidence limits,
not model-only/shadow readiness requirements. Provider readiness is secret-safe and does not probe
authentication unless the operator explicitly runs provider work.

Shadow rows are permanently non-public. Role-only odds cannot establish publication-safe edge.
Public reads use only active persisted prediction rows already marked publication eligible and
fail closed when current eligibility is not proven. Current production state remains zero public
predictions, `TIMESTAMP_GATE = PENDING`, `MARKET_STABILITY = UNAVAILABLE`, and
`FINAL_CHECK_UNAVAILABLE`.

Backend contract audit:

- Explore-like publication-eligible listing: available at `GET /api/v1/predictions`; safely empty.
- Per-match published prediction collection: available; safely empty without eligible evidence.
- Today fixture listing: `BACKEND_CONTRACT_GAP`.
- Match Detail fixture/result/statistics contract: `BACKEND_CONTRACT_GAP`.
- Public market-evaluation and availability-state contract: `BACKEND_CONTRACT_GAP`.
- Explicit stale/unavailable/Final Check response fields: `BACKEND_CONTRACT_GAP`.

These gaps are not filled with internal shadow evidence or invented values.

## Release and rollback

The intended schedule is metadata only: Tuesday 08:00 UTC covers Tuesday–Thursday; Friday 08:00
UTC covers Friday–Monday. No scheduler is active. Manual windows must be timezone-aware, positive,
no longer than seven days, and capped at twenty fixtures. The production CLI defaults to eight.

Before release: require a clean tree, full tests, current migration, valid configuration, secret
scan, healthy readiness, intended activation flags, database integrity, and public API isolation.
Use `python -m pitchvalue.operations.release_validation` and the operator status command. No paid
tooling is required.

Rollback is fail-closed: disable scheduler, publication, and external alerts; stop provider calls;
preserve run/event/quarantine/shadow evidence; revert the application commit; and migrate only
through a separately reviewed nondestructive plan. Never delete operational evidence as rollback.
For provider outage/auth revocation/quota exhaustion, database outage, stale run, report failure,
malformed payload, or uncertain publication evidence, stop, degrade, quarantine, or recover
explicitly. Never fabricate missing evidence.
