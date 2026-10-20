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

Google authentication, current-user retrieval, database-backed login sessions, and an authenticated streaming transcription relay are implemented. No passwords, general user API, AI assistance, user API-key storage, documents, embeddings, vectors, or payments are implemented. `.env`, virtual environments, and caches are ignored; `.env.example` contains placeholders only.

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

## Streaming transcription relay

`WS /api/transcription/stream?source=system|microphone` accepts only an explicit native `Authorization: Bearer <MeetGuide session>` header, never a browser cookie/query token. Browser Origin requests are rejected. After session validation, the relay opens the configured provider and sends `ready`. Clients then send bounded binary mono PCM16 at 16 kHz. Normalized `transcript` events contain `source`, `segment` (milliseconds relative to this connection), `text`, and `final`; partials may replace the same segment until final. `{"type":"finish"}` flushes final text, followed by `done`.

The provider boundary is `app/transcription/provider.py`. Default `gemini.py` uses the dedicated Gemini Live WebSocket transcription API, `gemini-3.5-transcribe-live`, with backend-only `GEMINI_API_KEY`. `deepgram.py` remains a dormant Nova-3 alternative. Selection is explicit; failures NEVER fall back to Deepgram. `api.py` continues to own authentication, framing, periodic session revalidation and cleanup. No migration is needed.

Manually set these non-secret values in the existing ignored backend environment, keeping all real credentials unchanged:

```dotenv
TRANSCRIPTION_PROVIDER=gemini
GEMINI_TRANSCRIBE_MODEL=gemini-3.5-transcribe-live
TRANSCRIPTION_LANGUAGE=en-US
```

The existing backend `GEMINI_API_KEY` is reused. Restart the API after changing selection. To deliberately use the dormant adapter instead, set `TRANSCRIPTION_PROVIDER=deepgram` with `DEEPGRAM_API_KEY` and `TRANSCRIPTION_MODEL=nova-3`. No automatic fallback or parallel provider usage occurs.

Gemini receives 100 ms batches of mono signed 16-bit little-endian PCM at 16 kHz, encoded as base64 in Live realtimeInput messages. No additional transcoding is performed. VERBATIM is intentional for the initial baseline: SMART can remove false starts/repetitions and resolve corrections, potentially changing request boundaries before local assembly. Automatic server VAD uses its provider defaults; no manual/hybrid endpointing or artificial per-sentence stream endings are added. Local 1.2-second quiet debounce / 3-second assembly remain unchanged. Generic vocabulary biasing includes Salesforce, Service Cloud, Sales Cloud, HubSpot, Zapier, Zendesk, Paystack, RevOps, Apex, SOQL, LWC and Omni-Channel; no private document vocabulary is supplied.

`interimInputTranscription` replaces the current hypothesis; `inputTranscription` finalizes it. Both arriving in one message are retained in order. Gemini Live has no word timestamps/confidence: segment identity uses monotonically increasing receipt-relative milliseconds (approximate, not speech-alignment timestamps), stable across interim/final updates. Separate finalized fragments remain separate events for the existing turn assembler.

Before the documented ten-minute upstream session limit, the adapter requests reconnection at 9.5 minutes; provider goAway does the same. Existing native backoff (up to 15 seconds) and new connection epochs discard stale queued audio. This renewal is not seamless: short visible gaps may lose speech and require long-meeting manual testing. Auth/configuration/quota errors are terminal until corrected and restarted; network failures reconnect without changing provider. No provider response bodies or credentials are logged. Setup acknowledgement is bounded to eight seconds, audio writes to three seconds; idle receive remains open because silence is valid.

Official wire contract: https://ai.google.dev/gemini-api/docs/live-api/live-transcribe . Provider audio processing is required; review Google account data-use/quota terms before using private audio. Automated tests use fake sockets only and do not prove live model access, quality, latency or free quota.

Use the installed `websockets` transport with Uvicorn's `--ws websockets-sansio --ws-max-size 8192 --ws-max-queue 8 --no-access-log --log-level warning`. Reverse proxies must support long-lived authenticated WebSockets; use TLS outside loopback development. Do not enable frame/body/header debug logs. Provider wire logging is explicitly disabled. Audio/transcripts exist only in bounded process/network buffers and are never written to files or PostgreSQL. The provider necessarily processes audio; request opt-out and retention behavior must be verified against the provider account/policy.

The relay uses fresh short-lived DB sessions only for authorization and revalidation (every 60 seconds), not long-running meeting transactions. Provider sockets use bounded buffers, keepalives and timeouts; stop/disconnect cancels sender/receiver tasks and closes upstream resources. Tests mock Google, database access and transcription providers. Synthetic native relay tests and the real local Uvicorn protocol smoke check require no cloud credentials and do not prove live provider accuracy.

## Context Library foundation

Authenticated web users can upload résumé/CV context, list documents, delete them and retrieve relevant chunks. The general `context_documents` / `context_chunks` schema and storage/index interfaces support adding other document types later; only `resume` is accepted now. No AI or embedding service is used. Desktop UI is unchanged.

### Setup and migration

Install `requirements.txt` in the existing virtual environment. Review migration `0003_context_library` before applying it manually:

```powershell
# Run from backend/, using the existing private .env. Never print its values.
.\.venv\Scripts\python.exe -m alembic upgrade head
```

This implementation did not apply the migration to Neon. Back up the database before schema changes. Restart the API after migration. The existing frontend origin must remain `http://127.0.0.1:5173`.

Local files default to `backend/.data/documents`, ignored by Git and never served publicly. `CONTEXT_STORAGE_DIR` can select an absolute private persistent directory; no setting change is required for local development. Restrict OS/NTFS access to the backend service account. Windows uses inherited NTFS ACLs, not POSIX mode bits. This checkout is in OneDrive: its default data directory may be synced by OneDrive. Use a dedicated private, non-synced encrypted volume for deployment/sensitive real documents. Back up PostgreSQL and private storage together; deleting a document cannot erase pre-existing backups/provider snapshots. There is no object-storage account or paid API requirement.

`DocumentStorage` is replaceable with a private object-storage adapter. Raw binaries stay out of PostgreSQL. Metadata, normalized extracted text and retrieval chunks are stored in PostgreSQL. Storage keys are random UUID identifiers, independent of user filenames; API responses never include storage keys/paths or full extracted text. Account deletion is restricted while documents exist so raw files cannot be orphaned through a user cascade.

### API contract

All endpoints require the existing session cookie. Mutations/retrieval POSTs require the exact frontend `Origin` for CSRF protection. Credentialed CORS supports DELETE and the upload filename header. No public file/download endpoint exists.

- `POST /api/context/documents`: raw file body (not multipart), `Content-Type: application/octet-stream`, `X-Document-Name: <URL-encoded UTF-8 filename>`. Returns document metadata (201).
- `GET /api/context/documents`: owned document metadata only.
- `DELETE /api/context/documents/{uuid}`: delete an owned document and its chunks/file (204); unknown and other-owner IDs both return 404.
- `POST /api/context/retrieve`: JSON `{"query":"Salesforce integration experience","limit":5,"document_id":null}`. Returns text, document/chunk IDs, document name/type, rank and BM25 score. No match returns an empty array. Other-owner document filters also return an empty array.

Upload limits: 5 MiB (declared and streamed body), 100 PDF pages, 200,000 extracted characters, up to 50 documents/account. PDF signature/parser checks, DOCX ZIP/OOXML checks and UTF-8/control-character checks validate contents in addition to extensions; browser MIME is not trusted. Encrypted, scanned/image-only, empty and malformed documents are rejected. No OCR. DOCX main-body paragraphs and table-cell text retain document order; headers/footers/text boxes and complex visual layout may not survive extraction. PDF text order depends on the source PDF. PDF parser work/decompression and DOCX ZIP expansion/entity limits are bounded; this remains a synchronous development ingestion path, not a bulk document-processing service.

Normalized paragraphs are packed into chunks up to 1,200 characters; oversized paragraphs split near words with about 160 characters overlap. `RetrievalIndex` provides a replaceable chunk/rank boundary. The initial adapter computes deterministic BM25 over owned ready chunks, with a small English synonym map (leadership/management, integration/API/automation). Scores are relative lexical relevance, not factual confidence or semantic understanding. No network call, paid embedding or vector database is involved. Ranking scans the account's bounded library at query time; no separate stale index or cross-user corpus exists.

Deletion first commits a `deleting` tombstone, excluding the document from retrieval; it then removes the private file and deletes the metadata/full text with cascading chunk deletion. A storage or final database failure returns a sanitized 503 and can be retried. Upload transaction failures attempt file cleanup. File storage and PostgreSQL cannot share an atomic transaction: an abrupt process crash during upload can leave an unreferenced private file, requiring operational reconciliation. Do not log request bodies, filenames/headers, extraction exceptions or query contents in reverse proxies/APM. Parser diagnostics are suppressed; application errors are sanitized. Database/filesystem backups have separate retention policies.

### Verification and manual check

Automated API tests use repository doubles with real temporary file storage; SQL ownership filters, PostgreSQL model/migration DDL and cascading constraints are checked offline. No SQLite or live Neon/Google connection is used. A live post-migration database check is still required.

1. Apply the reviewed migration, start the existing API from backend/, then run `npm run dev` from frontend/.
2. Open `http://127.0.0.1:5173`, sign in with Google and find **Context Library** above the existing landing content.
3. Upload a text-based PDF, DOCX or UTF-8 TXT résumé. Check name, format and Ready status. Refresh the page; the list should remain.
4. From the signed-in frontend browser DevTools console, test retrieval (the browser supplies Origin):

```javascript
await fetch('http://127.0.0.1:8000/api/context/retrieve', {
  method: 'POST', credentials: 'include',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query: 'Salesforce integration experience', limit: 5})
}).then(response => response.json())
```

Repeat with `leadership experience`; use a résumé containing those facts. Inspect text, document/chunk IDs, score and rank. No result is expected for unrelated terms. Avoid using a shared console with sensitive résumés.

5. Try an empty file, renamed executable, malformed PDF, scanned PDF or file above 5 MiB; expect a useful error and no new document.
6. Sign out and sign in with another Google account. The first account's list/content must be absent. Request its document ID through delete/retrieval: expect 404/empty results.
7. Return to the original account, delete the document and confirm removal. Refresh and rerun retrieval: no content remains available. Check the configured private file directory and database for removal if desired.
8. Check light/dark mode and a narrow viewport; the existing landing page remains unchanged outside the added authenticated library.

## Personalized Live Cue

The native desktop sends a confident finalized question event to `POST /api/cues/generate` using its existing opaque bearer session. Web cookies alone cannot call this native endpoint. Retrieval stays backend-side and always filters by the authenticated user. No migrations, transcript persistence or stored cues were added.

`app/cues/provider.py` defines the replaceable `CueProvider` protocol. The single adapter is Gemini 3.5 Flash-Lite over the existing httpx dependency; no new SDK, account connection UI or second provider was added. It uses stateless `generateContent`, structured JSON, no tools/search, temperature 0.2, a 2,200 output-token cap and bounded response bytes. Requests time out; there are no automatic billable retries.

### Manual configuration — no billing was enabled

The real `.env` was not changed. When ready, configure these backend-only variables yourself:

```dotenv
LIVE_CUE_ENABLED=true
LIVE_CUE_PROVIDER=gemini
LIVE_CUE_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=<your-private-key>
```

Until enabled and a key is supplied, generation returns a retryable configuration error; audio/transcription still work. Restart the API after changing configuration. Never use a `VITE_` variable for this key or put it into desktop code.

Google currently lists a free quota for this model, subject to account/region/quota eligibility. Paid standard pricing is currently $0.30 per million input tokens and $2.50 per million output tokens, including thinking. Check current pricing and quota before enabling anything: https://ai.google.dev/gemini-api/docs/pricing . This feature does not enable billing or buy credits.

**Use fictional, non-sensitive documents and conversations for free-tier testing.** Google's unpaid-service terms permit use of submitted inputs/outputs for product improvement and possible human review, and instruct users not to submit sensitive/confidential/personal information: https://ai.google.dev/gemini-api/terms . Paid-service data terms differ; review them before sending real résumé/conversation content. Disabling MeetGuide persistence does not override provider retention/data terms.

### Data minimization and answer contract

Each generation request contains the fixed answer instructions, question (at most 1,600 characters), at most six recent turns (at most 1,000 characters each / 4,000 total), and at most three relevant owned document chunks (1,200 characters each / 3,600 total). Short follow-up retrieval includes recent Them/You topics so references like 'the project' can find the earlier subject. No full résumé, raw file, audio, account email, session token, document filename or storage path is deliberately included. Selected excerpts can themselves contain personal data. Conversation is used to resolve references, not as verified personal-history evidence.

The model is asked for natural first-person speech, normally 85–150 words in 2–3 short paragraphs. Retrieved excerpts are delimited in `document_evidence`; the prompt treats them as untrusted data and the only support for personal history. It explicitly prohibits invented employers, technologies, projects, responsibilities, numbers, achievements and challenges, and preserves attribution, qualifications and negation. Conversation resolves references but does not establish personal facts. Missing specifics should lead to an honest bridge, supported transferable experience or a hypothetical approach.

The response contains paragraphs and evidence IDs, with no per-sentence claims or verbatim quotes. Normal paraphrasing, reordering, transitions and responsibility wording are allowed. Local checks enforce spoken length/paragraphs, reject coaching and unknown source IDs, and flag a narrow set of concrete unsupported anchors in personal-history assertions: recognized technology names, explicitly named employment/projects, digit-based quantities with units, and explicit sole credit. These checks deliberately do not compare arbitrary capitalized words or synonym groups. They are tripwires, not comprehensive semantic verification; an allowed answer is not proof of factual accuracy, and source references indicate excerpts used rather than independent certification.

There is no second LLM verification request. Successful normal generation uses one request. A local validation failure permits at most one conservative regeneration with the original bounded input and a fixed failure category; the rejected answer is not resent. If validation still fails, the answer is withheld with the existing retryable error. Provider/network failures are not automatically retried. Both generation attempts share the existing overall timeout and cancellation. This reduces normal latency/token cost; exceptional regeneration can add latency/cost within that deadline. Logs contain only fixed failure categories, never document text, conversation or answers. No cues/transcripts are persisted.

Application state remains in memory. Request bodies, provider errors, prompts and answers are not logged by this module. Keep body/header capture disabled in reverse proxies/APM. Disconnects cancel work where possible. Already received provider requests may still incur usage. The backend limits concurrent calls to two per account / eight per process; this is not a distributed quota or billing limit.

### Safe end-to-end test

1. Use a dedicated test account whose Context Library contains only a fictional CV. Remove real documents from that account; do not use a real meeting. Existing Context Library migrations must already be applied.
2. In the web app, upload a small fictional TXT CV with complete factual lines, for example: `Developed Salesforce integrations with external APIs.` and `Managed a team of six engineers.` Avoid real contact details.
3. Configure the variables above with an eligible test key, keeping billing disabled if free quota is available. Restart the existing API, then run `./start-desktop.ps1` from the project root and sign in with that same test account.
4. Start System Audio or Both, using headphones. Play a synthetic/system-audio question: 'How did you handle the Salesforce integration?' Wait for finalized Them text, question detection, then Preparing answer and a readable two-paragraph answer. Microphone-only questions must not trigger a cue.
5. Speak a fictional reply mentioning the integration, then play 'What was the biggest challenge?' Distinct questions now queue without a detection cooldown. Check that the cue follows the subject without inventing an undocumented challenge/result.
6. Ask about an unsupported system such as SAP S/4HANA. Expect an honest bridge/transferable documented fact plus a hypothetical approach; never claimed hands-on SAP experience. Empty/no-match context should produce a general hypothetical answer.
7. Repeat a detected question: it should not generate again within the existing duplicate cache. Ask distinct questions while an answer is preparing: all must queue and produce separate session-only cards in order.
8. Temporarily disable Live Cue in backend configuration and restart the API. Transcription/question detection should continue while the cue shows a retryable error. Re-enable, restart and click Retry answer. Do not paste any key into the UI.
9. Stop during preparation, restart, sign out and close/reopen the desktop app. Cues must clear and stale responses must not return. Restore `LIVE_CUE_ENABLED=false` when finished if you want generation disabled.

Automated tests use fake providers and httpx MockTransport, never live Google/Gemini or real document contents. No live provider or acoustic answer-quality test was performed during implementation.


## Gemini semantic intent

`POST /api/intent/classify` uses the existing native opaque bearer-session authentication and rejects browser Origin requests. It is a separate replaceable `IntentProvider` boundary; the first adapter is `GeminiIntentProvider`. It classifies transcript intent only, never writes a Live Cue answer or retrieves documents.

Optional `GEMINI_INTENT_ENABLED` defaults to `true`; the existing `LIVE_CUE_ENABLED`, `GEMINI_API_KEY` and `LIVE_CUE_MODEL` must also be configured. This reuses the current backend Gemini setup; no new credentials or provider installation is required. Real `.env` files are not modified by this milestone. Set the optional flag to false to test native deterministic fallback. Provider keys remain backend-only.

Input: candidate text (1,600 characters), up to six transcript turns (4,000 total characters), an optional prior request (1,600 characters), and an explicit continuation-eligibility flag. No résumé/context-library excerpts, cue-answer history or entire session is sent. Output: `kind` (`ACTIONABLE_REQUEST`, `CONTINUATION`, `FOLLOW_UP`, `NOT_ACTIONABLE`), `normalized_request`, `confidence`. The prompt forbids answering, inventing facts or adding requirements. Continuations across an ineligible boundary are rejected.

The classifier requests at most 384 output tokens, has an 8-second deadline, one in-flight call per account / four globally per process, a 32 KiB input cap and the existing bounded Gemini JSON transport. Error responses are sanitized and no-store; no transcript or key logging is added. Native routing deduplicates candidates and applies an additional session call budget. Unavailability, quota and malformed output cause deterministic fallback rather than stopping transcription. Existing answer retrieval/generation/grounding remain unchanged.

For a safe manual test, use a fictional context document and synthetic audio in the development desktop app. Ask the split Salesforce integration request, then “How did you undo” / “the Salesforce migration?” without removing a card. Both cards should remain. Ask three distinct questions while an answer is preparing, remove the middle completed card, then ask Q4. Stop/restart and sign out to verify the feed clears. The installed beta is unchanged; no installer is rebuilt here.
