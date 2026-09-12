# Supabase staging readiness

PitchValue targets Supabase Managed PostgreSQL as a future staging platform, but this package does
not deploy, connect to, or configure a production Supabase project. Alembic remains the sole
migration authority and migrations must use a direct PostgreSQL connection.

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
