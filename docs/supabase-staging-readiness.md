# Supabase staging readiness

PitchValue targets Supabase Managed PostgreSQL, but repository readiness does not itself deploy,
connect to, or designate a production Supabase project. Alembic remains the sole schema authority.
`DATABASE_URL` is the application/runtime connection (a session pool may be appropriate for the
long-running API); `DATABASE_DIRECT_URL` is the unpooled migration/maintenance connection used by
Alembic. Local development and tests may use one local URL for both. Staging and production require
both variables and `sslmode=verify-full` on each; certificate and hostname verification must not be
disabled. Inject credentials through the deployment's secret environment, never Git or `.env.example`.

The provider-neutral readiness contract distinguishes direct, session-pool, and transaction-pool
connections. It validates explicit TLS, migration connection mode, application pool size, prepared
statement compatibility, database reachability, and the exact Alembic revision. It neither changes
the selected deployment mode nor embeds credentials.

The current long-running FastAPI process uses SQLAlchemy connection pooling and is compatible with
a direct connection or a session pool once TLS and deployment pool limits are configured. A
transaction pool is not approved by default: it requires prepared statements to be disabled,
application pool size one for serverless-style deployment, and no reliance on session state,
cross-transaction cursors, temporary tables, LISTEN/NOTIFY, or session advisory locks.

Supabase currently recommends direct connections for migrations and persistent IPv6 backends,
session pooling for persistent IPv4 clients, and transaction pooling for transient/serverless
clients. Transaction pooling does not support prepared statements or durable session state. See
[Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres)
and [pooling limits](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits).

No Data API exposure, grants, RLS policy, authentication, Supabase-specific business logic, or
production secret is introduced here. If tables are later exposed through the Supabase Data API,
access grants and RLS require a separate security decision. Production deployment status remains
NOT DEPLOYED.

## Controlled cutover prerequisites

Use a dedicated, explicitly identified PitchValue project. Before applying Alembic to its `public`
schema, verify that the Data API cannot expose application tables (especially `app_users`, auth
sessions, and other account records); otherwise obtain an approved grants/RLS or private-schema
design first. Supabase-managed `auth.*` is outside PitchValue's Alembic scope. Do not treat an
unrelated project as a migration target.

Create a full source `pg_dump -Fc` backup, record its checksum, and prove it restores into a
temporary local PostgreSQL database. On the target, run the existing Alembic chain through the
direct URL before importing data. The migrations seed `competitions`; reconcile those seed rows
against the source before a data-only transfer, and do not import `alembic_version` as data. The
`auth_sessions.replaced_by_session_id` self-reference can produce a `pg_dump --data-only` warning;
verify the actual restore and all foreign keys rather than suppressing the warning or disabling
triggers. Reconcile every table, all identity sequences, constraints, indexes, deterministic data
hashes, current-season rows, and existing application auth data before changing authority.

For final cutover, pause every local writer, take a final snapshot, transfer/reconcile the final
delta, switch only the runtime secret configuration, run Today/auth/engine-shadow/health smoke
checks, then resume writers and verify new writes land only in Supabase. Keep the local database
intact. A rollback to local is straightforward only before unique Supabase writes; afterward,
pause writers and design a reverse-sync reconciliation before switching back. Scheduler and public
publication remain disabled unless independently authorized.
