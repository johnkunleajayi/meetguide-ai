# MeetGuide AI API

Python/FastAPI modular monolith. PostgreSQL with SQLAlchemy 2.x and psycopg is the only supported database. The first domain model is User; no authentication or user API is implemented.

## Setup (Windows PowerShell)

Use Python 3.14 (verified with 3.14.6).

```powershell
cd C:\Users\JOHN-KUNLE\OneDrive\Desktop\meetguide-ai\backend
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Replace every placeholder in the ignored `.env`:

- `APP_NAME`: `MeetGuide AI API` for the expected health response.
- `APP_ENV`: `development`, `test`, or `production`.
- `DATABASE_URL`: your actual `postgresql+psycopg://username:password@host:port/database` URL. URL-encode special characters in credentials. A database host and database name are required. SQLite and other drivers are rejected.
- `FRONTEND_ORIGIN`: exact web origin, normally `http://127.0.0.1:5173`.
- `DESKTOP_ORIGIN`: exact desktop Vite origin, normally `http://127.0.0.1:1420`.

The defaults match those two development origins. `localhost` and `127.0.0.1` are different origins; use the actual client URLs. Origins cannot contain credentials, wildcard hosts, or paths. Environment variables override `.env`, which is loaded from the backend directory regardless of the working directory. No real credentials are supplied or stored by this foundation.

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/api/health
- Swagger: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json

Expected health response:

```json
{"status":"ok","service":"MeetGuide AI API"}
```

Health is process liveness, not database readiness. Creating the engine does not open a PostgreSQL connection. Startup, health, and Swagger therefore work without a live database, provided configuration is valid. The engine is disposed during shutdown. CORS allows only the configured web and desktop origins, GET requests, and Content-Type; credentials are disabled because authentication does not exist yet.

To verify liveness without a database or `.env`, you can set `DATABASE_URL=postgresql+psycopg://127.0.0.1:5432/meetguide` in the current shell. This credential-free URL is only for liveness checks; it does not demonstrate a working database connection.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=..\work\pytest-temp
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

Tests provide isolated configuration, block SQLAlchemy connections for startup/health checks, and require no PostgreSQL server. Offline Alembic commands require a valid database URL but do not connect. `heads` now reports `0001_create_users`. This migration is prepared for manual review and has not been applied by this milestone.

## Database and migrations

A local or reachable PostgreSQL server and a provisioned database/role are prerequisites for real database access and online migrations. This foundation does not install PostgreSQL or create roles/databases. No SQLite fallback exists.

```powershell
# Once PostgreSQL and DATABASE_URL are available:
.\.venv\Scripts\python.exe -m alembic current
# When a future module intentionally adds models:
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "Describe schema change"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The first migration, `0001_create_users`, creates only the users table and its unique email index. Do not apply it until it has been reviewed; this milestone does not run online migrations. Future model modules should import the shared `Base` and register in `app/models/__init__.py` so Alembic sees their metadata. Future API modules register their routers in `app/api/router.py`. Routes that need a database can use `Depends(get_db)` from `app/db/session.py`; they own commit/rollback decisions, while the dependency closes the session.

## Structure

- `app/api/`: API router and health endpoint/response schema.
- `app/core/config.py`: validated Pydantic Settings.
- `app/db/`: PostgreSQL engine, session management, declarative base.
- `app/models/`: User model and model registry imported by Alembic.
- `app/main.py`: application factory, lifecycle, CORS.
- `alembic/`: migration environment/template and first, unapplied users migration.
- `tests/`: startup, liveness, Swagger, CORS, configuration, User metadata, and offline migration tests.

No authentication, user API, audio, transcription, AI providers, key storage, sessions, documents, embeddings, vectors, WebSockets, or payments are implemented. `.env`, virtual environments, and caches are ignored; `.env.example` contains placeholders only.

## User model milestone

`User` uses the shared declarative base and native PostgreSQL UUID values. UUID v4 IDs are generated by SQLAlchemy on insert, without a PostgreSQL extension. Email is required (up to 320 characters), unique, and indexed by a single unique index (`ix_users_email`). Uniqueness uses normal PostgreSQL, case-sensitive text semantics; no email normalization or authentication is implemented. Name (up to 255 characters) and avatar URL (text) are nullable.

Both timestamps are non-null `TIMESTAMP WITH TIME ZONE` columns with database `now()` defaults. SQLAlchemy emits `updated_at = now()` for updates that do not explicitly supply a timestamp; this is not a database trigger, so direct SQL writers must manage updates themselves.

`tests/test_user_migration.py` renders the migration through an offline PostgreSQL migration context and compares its complete table/index DDL with model metadata. It does not load `.env`, run Alembic's online environment, connect to a database, or apply DDL.
