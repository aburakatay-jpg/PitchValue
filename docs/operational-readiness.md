# Operational readiness

TASK 23 hardens and validates the implemented PitchValue backend chain without changing any
model, market, scoring, or publication-policy semantics:

`historical data -> precomputed orchestration result -> atomic persistence -> current cache read
-> publication-filtered API -> liveness/readiness`

## Runtime dependencies and startup

The API requires a valid external `DATABASE_URL`, reachable PostgreSQL, Alembic revision
`20260913_0011`, and a readable `prediction_snapshots` table. Configuration fails clearly when
the database URL is missing or unsupported. Secrets remain outside source control and settings
representations redact the URL. Runtime request handlers never run migrations automatically.

`GET /health` is process liveness and intentionally does not touch PostgreSQL. `GET /ready` is
dependency readiness: it verifies the exact expected migration revision and access to prediction
persistence. A database, schema, or revision failure returns the existing deterministic 503 error
envelope without exposing connection details. The read-only release command
`python -m pitchvalue.operations.release_validation` reports machine-readable JSON and exits
nonzero unless connectivity, revision, and prediction storage are ready.

An empty prediction table is not the same as an unavailable prediction database.

Operational failures must not be converted into successful empty prediction responses.

## Failure-stop persistence and current reads

Each MATCH_RESULT selection set is written inside one transaction boundary. A constraint,
connection, or conflicting-payload failure rolls the attempted set back. Existing versioned
evidence is neither deleted nor overwritten by a failed new version.

A persistence failure must not create a partially publication-visible match prediction.

Semantic uniqueness plus a canonical payload hash makes identical replay idempotent and rejects
conflicting replay. Different model, policy, or orchestrator versions coexist. Current reads first
choose the newest active semantic version, then apply publication eligibility; therefore a newer
non-eligible version suppresses stale fallback to an older eligible version. Invalidated and
superseded rows stay in audit history but disappear from current/public reads.

Prediction API reads do not trigger model recomputation.

Application restart recreates the pooled database resource, not predictions. Persisted records
remain deterministic and readable after shutdown/startup. Request-scoped connections are closed
by their context boundary and the lifespan disposes the pool on shutdown. Concurrent reads are
read-only; concurrent identical writes converge on one DB-enforced semantic record set.

## Evidence and publication safety

`prediction_as_of`, `generated_at`, persistence time, and market `observed_at` remain distinct.
No operational layer synthesizes an exact market timestamp.

Historical ROLE_ONLY_COMPARISON evidence cannot become a production pick.

Role-only evidence stays non-publication-eligible through persistence, repository selection, and
the API. Exact-time synthetic evidence is exposed only when the upstream orchestration result
already marks it eligible. Persistence and transport preserve decisions rather than recomputing
them. Missing Bet Score and unavailable components remain `NULL`/unavailable, never numeric zero.

The historical database currently has no non-null `data_quality.quality_score`. Calibration was
rejected and there is no approved stability-score semantic. Consequently real historical
evidence cannot currently produce a complete Bet Score or a publication-ready prediction. This
is an evidence-readiness limitation, not an orchestration or persistence defect.

## Operational visibility and security

Readiness failures, persistence failures, and invalidations emit concise operational events with
stable event text and identifiers. Public errors use the established request-correlated envelope;
stack traces, passwords, and database URLs are not returned. The system does not log each model
calculation.

Public prediction reads are currently unauthenticated. That can be acceptable for an internal
technical boundary, but authentication and abuse controls are launch prerequisites if access
must be restricted. Premium entitlement is not implemented; it is outside the engine/backend
foundation and is required before a paid-product launch where product rules demand it. Canonical
prediction persistence is match-based, never per-user recomputation.

## Operational gaps

There is no live fixture/odds provider, refresh scheduler, or autonomous production generation
loop. The real `prediction_snapshots` table is intentionally empty. The architecture can serve
persisted outputs, but no code in TASK 23 creates live predictions or claims that autonomous
production operation is active.

## Release gates

The technical release gate requires all of the following:

- PostgreSQL reachable and Alembic exactly at `20260913_0011`.
- Historical Data Gate PASS and canonical historical counts unchanged.
- Prediction persistence schema readable; real operational validation performs no writes.
- Full automated, focused regression, formatting, lint, typing, and mobile checks pass.
- Atomic/idempotent/conflict persistence tests pass.
- Current-version, invalidation, role-only, empty-vs-failure, restart, and API safety tests pass.
- No secrets, credentials, raw datasets, database files, or generated artifacts are committed.
- The working tree contains only reviewed TASK 23 changes and no critical code defect is known.

Separate launch prerequisites are live provider integration, refresh/generation scheduling,
operational deployment/monitoring, production authentication and entitlement where required,
non-missing quality evidence, accepted calibration/stability evidence, and broader real-world
robustness validation. Profitability and public recommendation readiness require evidence beyond
technical code completion.

Code completion does not imply profitability or product launch readiness.

TASK 23 does not add model development, threshold tuning, live acquisition, entitlement, mobile
features, LLM prediction logic, ROI, Kelly staking, or settlement behavior.
