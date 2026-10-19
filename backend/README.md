# MeetGuide AI API

Python/FastAPI modular monolith. PostgreSQL with SQLAlchemy 2.x and psycopg is the only supported database. User and database-backed Session models support Google OIDC authentication. No other domain features are implemented.

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
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000 --no-access-log
```

- Health: http://127.0.0.1:8000/api/health
- Swagger: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json

Expected health response:

```json
{"status":"ok","service":"MeetGuide AI API"}
```

Health is process liveness, not database readiness. Creating the engine does not open a PostgreSQL connection. Startup, health, and Swagger therefore work without a live database, provided configuration is valid. The engine is disposed during shutdown. CORS allows credentials only for the configured web and desktop origins, GET/POST requests, and Content-Type. Browser fetch calls must use credentials: "include". Logout requires an exact trusted Origin header.

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

Tests provide isolated configuration, block SQLAlchemy connections for startup/health checks, and require no PostgreSQL server. Offline Alembic commands require a valid database URL but do not connect. `heads` now reports `0002_sessions`, which follows `0001_create_users`. The sessions migration is prepared for manual review; this milestone does not apply it or connect to Neon.

## Database and migrations

A local or reachable PostgreSQL server and a provisioned database/role are prerequisites for real database access and online migrations. This foundation does not install PostgreSQL or create roles/databases. No SQLite fallback exists.

```powershell
# Once PostgreSQL and DATABASE_URL are available:
.\.venv\Scripts\python.exe -m alembic current
# When a future module intentionally adds models:
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "Describe schema change"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The existing `0001_create_users` migration creates users. The new `0002_sessions` migration creates database-backed login sessions. Review and apply it manually before testing real Google login. This implementation does not run online migrations. Future model modules should import the shared `Base` and register in `app/models/__init__.py` so Alembic sees their metadata. Future API modules register their routers in `app/api/router.py`. Routes that need a database can use `Depends(get_db)` from `app/db/session.py`; they own commit/rollback decisions, while the dependency closes the session.

## Structure

- `app/api/`: health and authentication endpoints/response schemas.
- `app/core/`: validated settings, Authlib client setup, session-token and authentication logic.
- `app/db/`: PostgreSQL engine, database session dependency, declarative base, and authentication persistence.
- `app/models/`: User/Session models and registry imported by Alembic.
- `app/main.py`: application factory, lifecycle, CORS.
- `alembic/`: migration infrastructure, existing users revision, and new unapplied sessions revision.
- `tests/`: startup, liveness, Swagger, CORS, configuration, User metadata, and offline migration tests.

Only Google authentication, current-user retrieval, and database-backed login sessions are implemented. No passwords, general user API, audio, transcription, AI providers, API-key storage, documents, embeddings, vectors, WebSockets, or payments are implemented. `.env`, virtual environments, and caches are ignored; `.env.example` contains placeholders only.

## User model milestone

`User` uses the shared declarative base and native PostgreSQL UUID values. UUID v4 IDs are generated by SQLAlchemy on insert, without a PostgreSQL extension. Email is required (up to 320 characters), unique, and indexed by a single unique index (`ix_users_email`). Uniqueness uses normal PostgreSQL, case-sensitive text semantics; no email normalization or authentication is implemented. Name (up to 255 characters) and avatar URL (text) are nullable.

Both timestamps are non-null `TIMESTAMP WITH TIME ZONE` columns with database `now()` defaults. SQLAlchemy emits `updated_at = now()` for updates that do not explicitly supply a timestamp; this is not a database trigger, so direct SQL writers must manage updates themselves.

`tests/test_user_migration.py` renders the migration through an offline PostgreSQL migration context and compares its complete table/index DDL with model metadata. It does not load `.env`, run Alembic's online environment, connect to a database, or apply DDL.

## Google authentication and sessions

Endpoints:

- `GET /api/auth/google/login`: starts the Google authorization-code flow with state, nonce, and PKCE S256 managed by Authlib.
- `GET /api/auth/google/callback`: validates state and the signed identity token (issuer, audience, expiry, nonce), requires a verified email, normalizes it with `strip().lower()`, creates/updates the User, creates a session, and redirects to `FRONTEND_ORIGIN`.
- `GET /api/auth/me`: returns id, email, name, avatar_url, created_at, and updated_at; returns 401 for missing, revoked, invalid, or expired sessions.
- `POST /api/auth/logout`: deletes the current session and clears its cookie. Include `Origin` matching either configured client. Repeating logout is safe.

Google client configuration is server-only: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. The configured callback must exactly match the Google Web OAuth client's redirect URI. No real values are included in this repository. Credentials and Google access/identity tokens are never returned by these endpoints or persisted in session rows/cookies.

For loopback development, the existing settings work with the frontend/API on 127.0.0.1 at their configured ports. Do not mix localhost and 127.0.0.1. Real credentialed client calls must be same-site for SameSite=Lax cookies; neither client is changed in this milestone.

Session security:

- The `meetguide_session` cookie holds a random 256-bit opaque token. PostgreSQL stores only its SHA-256 hash; no password-style hashing is needed for a high-entropy random token.
- Cookies are HttpOnly, SameSite=Lax, host-only, and Path=/. Session lifetime defaults to seven days and is configurable with `SESSION_TTL_SECONDS` (60 seconds to 30 days). Expiry is enforced by the database lookup as well as cookie Max-Age.
- Successful sign-in rotates the browser's previous session. Logout removes the row immediately. Missing profile claims do not erase existing name/avatar data; new avatar URLs must use HTTPS.
- Authentication responses use Cache-Control: no-store. Provider/database errors return generic messages. The documented Uvicorn command disables access logs to avoid logging OAuth callback query parameters.
- A separate signed, HttpOnly `meetguide_oauth_state` cookie is limited to the Google login/callback path and ten minutes. It contains only handshake data, never Google credentials or login tokens. It is cleared after callback handling.
- In local development, `AUTH_STATE_SECRET` may be omitted; an ephemeral process-local signing key is generated. Restarting the server invalidates pending login handshakes, not database-backed login sessions. Use a stable random `AUTH_STATE_SECRET` of at least 32 characters for multiple workers, and always in production.
- Production defaults to Secure cookies, rejects explicitly disabling Secure, and requires an HTTPS callback and stable state-signing key when Google login is configured. `SESSION_COOKIE_SECURE=false` is accepted only for loopback development/testing. Production still requires normal HTTPS deployment.

Users are matched by normalized, verified Google email; no separate Google-account linking or password authentication is introduced. The existing users table must not contain ambiguous duplicate case variants of an email. Expired session rows stop authenticating immediately; scheduled row cleanup is not implemented.

Tests mock Google discovery/token/JWKS HTTP requests, generate disposable test RSA keys, and exercise actual Authlib claim/signature checks. Authentication persistence uses an in-memory test double (not a database fallback); SQLAlchemy PostgreSQL query behavior and migration DDL are tested separately with mocks/offline compilation. Tests never read the real .env or connect to Neon. Live database/authentication integration is pending manual application of `0002_sessions` and a manual Google flow.

## Desktop authentication handoff

The existing Google login route optionally accepts `desktop_port` (1024–65535), a random 43-character `desktop_state`, and a 43-character S256 `code_challenge`. The signed Google handshake cookie binds these to the validated OAuth flow. Without these parameters the web redirect/cookie behavior is unchanged. Desktop redirects are constructed internally as `http://127.0.0.1:<port>/callback`; arbitrary redirect hosts/paths are never accepted.

After Google validation, the desktop branch upserts the same User and creates a **60-second one-use handoff**, not a browser login cookie. The code combines a random 256-bit nonce with its public PKCE challenge. Its namespaced SHA-256 hash is stored in an ordinary sessions row; the code is never accepted as a session token. No schema changes or new migrations are required. Abandoned rows expire and are handled by the existing expired-session cleanup policy (no automatic cleanup job is currently implemented).

- `POST /api/auth/desktop/exchange`: JSON `code` and `verifier`. Validates S256, atomically consumes an unexpired handoff with PostgreSQL DELETE/RETURNING, and inserts the normal hashed opaque session in the same transaction. Returns `session_token` only to the native Rust client with Cache-Control: no-store. Codes cannot be replayed across workers.
- `GET /api/auth/desktop/me`: requires `Authorization: Bearer <opaque session>` and returns the existing user schema.
- `POST /api/auth/desktop/logout`: revokes that bearer session. These native routes never fall back to browser cookies; the web logout Origin/CSRF policy remains unchanged.

Google secrets remain server-only. There is no JWT or second user/session system. Native calls do not use CORS or browser cookies; no CORS expansion is needed. Keep HTTPS outside loopback development, a stable AUTH_STATE_SECRET across server workers, and access/body/header logs disabled for authentication. Continue using the existing backend Google Web OAuth client/redirect URI. Restart the API after updating code; do not apply any migration for this change.

Desktop session tokens are kept by Rust in Windows Credential Manager and never exposed to React. See `../desktop/README.md` for setup, security boundaries, and manual login/restart/logout checks.
