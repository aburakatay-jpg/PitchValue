# Prediction persistence and cache

TASK 21 adds the durable boundary downstream of the deterministic TASK 20 orchestrator. The
database stores the supplied result; it does not derive probabilities, edge, agreement, Bet Score,
or policy decisions. Prediction persistence does not recompute model or policy logic.

## Record and identity

`prediction_snapshots` stores one row per match, market, and selection. Its DB-enforced semantic
identity includes the match, `prediction_as_of`, market, selection, model and feature profile,
orchestrator and policy versions, edge and no-vig versions, bookmaker, market role/timing, and
market mapping/normalization/quality-policy versions. A surrogate key is only a storage key.
There is no user dimension: Canonical prediction persistence is match-based, not user-based.

Replaying an identical semantic payload returns `unchanged`. A different payload under the same
semantic identity is rejected rather than silently overwriting evidence. New model, policy, or
orchestrator versions coexist with older records, which remain queryable. A SHA-256 fingerprint of
canonical, sorted JSON makes replay comparison auditable; process-dependent object representations
and operational timestamps are excluded from that fingerprint.

## Time and market evidence

`prediction_as_of` is the evidence cutoff, `generated_at` is when the engine produced the result,
and `persisted_at` is when the database accepted it. prediction_as_of and generated_at are distinct timestamps.
Market `observed_at` and timing semantics remain independent from all three.

The repository never substitutes generation, persistence, import, staging, or prediction time for
an unknown market timestamp. Historical `role_only` timing remains NULL.
Historical ROLE_ONLY_COMPARISON evidence remains non-publication-eligible when persisted. A database check
also prevents role-only records from becoming publication eligible through a direct write.

Future exact-time evidence is representable: publication-eligible data must retain an exact market
timestamp at or before `prediction_as_of`, exact comparison status, and eligible market quality.
Persistence preserves the engine's eligibility decision; it does not infer one.

## Evidence and explainability

Searchable values—including probability, odds, market probability, edge, score, decision,
publication eligibility, versions, role, timing, and quality—are typed columns. Decimal values use
PostgreSQL `numeric`, avoiding lossy float conversion. Components and gates use deterministic JSON
arrays; blockers and diagnostics use stable text-token arrays. Lineage retains the canonical source
match provider reference, staging event, source field, and mapping/normalization/quality versions.

Bet Score is nullable. Its completeness state and each component's availability are retained.
Unavailable Bet Score components are persisted as unavailable, not as numeric zero. Policy
decision and publication eligibility are separate fields, so storing a simulated PICK-like policy
class does not publish role-only historical evidence.

## Atomic writes, invalidation, and cache reads

A match result is written in one transaction/savepoint. If any HOME/DRAW/AWAY row fails, none of
that logical write remains. The result reports created or unchanged counts explicitly. Storage
validation may reject an inconsistent payload, but no value is recalculated.

Invalidation and supersession mark evidence unusable without deleting audit history. Active current
reads select the newest `prediction_as_of`, then `generated_at`, for each match/market/selection.
Publication reads filter the persisted `publication_eligible` field and do not rerun policy gates.
Batch reads accept fixture match IDs and invoke no model code, enabling one shared daily cache rather
than per-user recomputation.

## Boundary

Internal read contracts expose diagnostics and lineage while identifying an active,
publication-eligible public candidate. TASK 21 does not expose a public API. TASK 22 may map these
cached records into an HTTP contract, but must not recalculate or promote their decisions.

TASK 21 adds no fixture or odds provider, network call, mobile behavior, LLM dependency, staking,
Kelly calculation, ROI calculation, or settlement.
