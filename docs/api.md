# PitchValue API foundation

The backend is a small FastAPI application built through `create_app()`. It exposes system
health routes and a version namespace only; football, prediction, user, subscription, and AI
business APIs are intentionally deferred.

## Architecture

`pitchvalue.api.app.create_app(settings=None, database_factory=...)` builds isolated application
instances for production and tests. Importing the package or constructing an application does
not connect to PostgreSQL. FastAPI lifespan starts one SQLAlchemy Core engine and its connection
pool immediately before serving, then disposes it during shutdown. No ORM declarations mirror
the canonical schema.

The route layout is:

- `GET /health` — process liveness only; never checks PostgreSQL.
- `GET /ready` — executes `SELECT 1`; returns 200 when PostgreSQL is reachable and a safe 503
  envelope otherwise.
- `GET /api/v1` — identifies the V1 namespace; it returns no product data.

FastAPI OpenAPI remains available at `/openapi.json`, with interactive development documentation
at `/docs` and `/redoc`.

## Local startup

Install the project and load the local public configuration as described in the root README.
PowerShell does not load `.env` automatically, so export `DATABASE_URL` and any overrides in the
current shell. Then run either:

```powershell
pitchvalue-api
```

or:

```powershell
python -m uvicorn pitchvalue.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Use reload only for local development. The default port is 8000.

## Configuration

- `DATABASE_URL` — required PostgreSQL SQLAlchemy URL; treated as secret.
- `PITCHVALUE_ENV` — `development`, `test`, or `production`.
- `API_HOST` — bind host, default `127.0.0.1`.
- `API_PORT` — bind port, default `8000`.
- `CORS_ALLOWED_ORIGINS` — comma-separated exact HTTP(S) browser origins.
- `LOG_LEVEL` — standard Python log level.

Wildcard CORS is rejected. Credentialed CORS is disabled. Local defaults permit the documented
Expo web development origins only; production defaults to no allowed origins.

## Request and error behavior

Every response includes `X-Request-ID`. Incoming IDs containing only letters, numbers, `.`, `_`,
`:`, or `-` are preserved up to 128 characters; other values are replaced with a generated ID.
Access logs include method, path, status, duration, and request ID. Bodies, tokens, database URLs,
and credentials are not logged.

Application, validation, not-found, readiness, and unexpected errors use this stable shape:

```json
{
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "Service is not ready",
    "request_id": "..."
  }
}
```

Foundational codes are `VALIDATION_ERROR`, `NOT_FOUND`, `SERVICE_UNAVAILABLE`, and
`INTERNAL_ERROR`. Raw exception and database connection details are never returned.

## Mobile and LAN access

The mobile client uses `EXPO_PUBLIC_API_BASE_URL`. A physical iPhone cannot reach the Windows
API through `localhost`, because that name refers to the phone itself. Bind the development API
to an appropriate network interface and set the mobile public base URL to
`http://<WINDOWS-LAN-IP>:8000`. Do not hard-code a machine address or put secrets in any
`EXPO_PUBLIC_*` variable.

## Verification

Run from the repository root:

```powershell
python -m pytest tests/test_api.py
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

Authentication, authorization, rate limiting, production security headers, business APIs,
prediction logic, subscriptions, notifications, AI, background jobs, and deployment
containerization remain deferred.
