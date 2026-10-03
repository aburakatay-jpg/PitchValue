# Scheduled fixture refresh

The production fixture refresh is a dedicated provider-only command:

```text
python -m pitchvalue.operations.scheduled_refresh --scheduled-for 2026-10-06T08:00:00Z
```

Only Tuesday and Friday at 08:00 UTC are accepted. The existing schedule contract resolves three
local fixture dates on Tuesday and four on Friday. Each date produces one paginated, maximum
24-hour `fixture_payloads()` sequence. The command never scans stale database dates, requests odds,
runs models, writes predictions, or creates shadow-analysis evidence.

`SCHEDULER_ENABLED` is not required by this command. That flag remains part of runtime readiness
semantics; the separately reviewed GitHub Actions workflow is the explicit activation boundary for
this bounded operation. Manual workflow runs must supply a valid configured `scheduled_for` value.
Scheduled jobs derive 08:00 UTC from the runner's current UTC date; if an exceptional delay crosses
into a non-configured day, command validation fails closed instead of refreshing the wrong horizon.

The workflow uses one non-cancelling concurrency group, so scheduled/manual overlap queues instead
of terminating an active refresh. The command stores its deterministic logical identity, attempt,
scheduled time, local date horizon, fixture counts, source, result, and started/completed evidence in
the existing operational tables. No schema migration is required.
