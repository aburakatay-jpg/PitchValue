# PitchValue

Minimal development foundation for the PitchValue Python and PostgreSQL codebase.
Product features and football-domain data are intentionally outside this bootstrap.

The canonical schema and its integrity policy are documented in
[`docs/database.md`](docs/database.md).
The football-data.co.uk raw and staging foundation is documented in
[`docs/ingestion-football-data-uk.md`](docs/ingestion-football-data-uk.md).

## Prerequisites

- Python 3.12, 3.13, or 3.14
- Docker with Docker Compose
- Git

## Setup

Create and activate a virtual environment in PowerShell, then install the project:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

The example values are for local development only. Change them if needed, and keep
`.env` untracked. Export `DATABASE_URL` into the current shell before commands that
connect to PostgreSQL. PowerShell does not load `.env` automatically:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://pitchvalue:local-development-only@localhost:5432/pitchvalue"
```

## PostgreSQL

Validate and start the single local service:

```powershell
docker compose config
docker compose up -d postgres
docker compose ps
```

The host port defaults to `5432` and can be changed with `POSTGRES_PORT`. Database
data is retained in the named `pitchvalue_postgres_data` volume.

## Migrations

Apply migrations, inspect the current revision, or roll back one revision:

```powershell
python -m alembic upgrade head
python -m alembic current
python -m alembic downgrade -1
```

## Verification

Run the tests and quality checks from the repository root:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

To apply formatting, run `python -m ruff format .`.
