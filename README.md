# MeetGuide AI

**Your real-time AI meeting assistant.**

## Architecture

```text
meetguide-ai/
├── frontend/     MeetGuide web application
├── desktop/      MeetGuide desktop companion
├── backend/      MeetGuide FastAPI API
├── .gitignore
└── README.md
```

A single Git repository at the project root contains three independent applications:

- `frontend/`: the existing React + TypeScript + Vite + Tailwind web application. The roadmap includes the marketing website, signup/login, dashboard, AI provider connections, documents/context, session preparation, account/settings, and desktop downloads. Public marketing (`/`), an authenticated preparation workspace (`/app`), cookie-based Google authentication, and Context Library document management are implemented. The remaining web roadmap is deferred.
- `desktop/`: a separate Windows-first Tauri 2 + React + TypeScript + Vite + Tailwind companion for use during meetings. The shell includes brand, tagline, Ready status, theme toggle, a disabled Start Session button, and native Google sign-in using the shared backend. See `desktop/README.md` for secure persistence and manual verification.
- `backend/`: MeetGuide FastAPI API, a modular monolith with PostgreSQL, SQLAlchemy 2.x, psycopg, Alembic, and environment-based settings. Health/configuration/database infrastructure, User/Session models, and Google authentication are implemented. Web and desktop share accounts and database-backed opaque sessions.

## Web development

Requires Node.js 22.12+ (or Node.js 24 LTS) and npm.

```powershell
cd C:\Users\JOHN-KUNLE\OneDrive\Desktop\meetguide-ai
cd frontend
npm install
npm run dev
```

Use the URL printed by Vite (normally http://127.0.0.1:5173).

```powershell
npm run typecheck
npm run build
npm run preview
```

The web source and existing visual design are preserved. The public product demonstration uses fictional content and frontend-only state transitions; it captures no audio and calls no transcription or AI services.

### Web routes and responsibilities

- `/`: public marketing website, accessible signed in or signed out; no private Context Library is mounted or fetched here.
- `/app`: authenticated preparation workspace with purpose/objective, reusable document upload/selection, and account controls. Signed-out visitors see a sign-in gate using the existing backend Google flow.
- Live transcription and Personalized Live Cue run in MeetGuide Desktop, not in the web workspace.

Public Sign in/Get started and the workspace sign-in gate record only a fixed `/app` navigation intent in session storage. After the existing Google callback returns to `/`, the successful session check opens `/app`. No credentials or tokens are stored in browser storage. If session storage is unavailable, use Open Workspace after sign-in. Signed-in users can still browse `/`; signing out from the workspace returns there only after backend logout succeeds.

React Router keeps pages, layouts and the authentication gate separate. Auth and document API calls retain session cookies and existing Origin protections. For production hosting, configure an SPA fallback to `index.html` for frontend routes such as `/app` (not backend `/api` routes); Vite dev/preview already handle this. Refreshing `/app` must serve the frontend entry point.

Run frontend regression tests with `npm test` from `frontend/`.

## Desktop development

Windows native development requires the MSVC Rust toolchain, Microsoft C++ Build Tools with the C++ desktop workload and Windows SDK, and Microsoft Edge WebView2 Runtime. See https://v2.tauri.app/start/prerequisites/.

```powershell
cd C:\Users\JOHN-KUNLE\OneDrive\Desktop\meetguide-ai\desktop
npm install
npm run typecheck
npm run build
npm run tauri dev
```

`npm run dev` runs only the React shell in the browser at http://127.0.0.1:1420. `npm run tauri dev` starts Vite and launches the native Windows window. `npm run build` builds the React shell; `npm run tauri build` additionally builds the native executable and NSIS installer.

### Project-local Rust toolchain

If using the toolchain installed for this checkout rather than a system Rust installation, activate it in the current PowerShell session before running Tauri:

```powershell
# Run from desktop/
$env:CARGO_HOME = (Resolve-Path ..\work\tools\cargo).Path
$env:RUSTUP_HOME = (Resolve-Path ..\work\tools\rustup).Path
$env:PATH = "$env:CARGO_HOME\bin;$env:PATH"
npm run tauri dev
```

The local toolchain and downloads live under ignored `work/`; they are not committed and will not be present in a fresh clone. On other machines install the documented Windows prerequisites normally.

## Desktop files

- `desktop/src/App.tsx`: shell with native authentication controls; meeting session controls remain disabled.
- `desktop/src/hooks/useTheme.ts`: system-aware light/dark mode with optional stored preference.
- `desktop/src/styles.css`: navy/slate/blue visual tokens and responsive shell styling.
- `desktop/src-tauri/`: native window, browser handoff, backend session client, and Windows Credential Manager storage.
- `desktop/src-tauri/capabilities/default.json`: only four account commands for the local main window; no generic shell/network/storage access.
- `desktop/src-tauri/icons/`: branded native application icons.

## Backend development

See [backend/README.md](backend/README.md) for configuration and database prerequisites. Python 3.14.6 was used for verification.

```powershell
cd C:\Users\JOHN-KUNLE\OneDrive\Desktop\meetguide-ai\backend
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Replace the placeholders in .env with your configuration.
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Health: http://127.0.0.1:8000/api/health. Swagger: http://127.0.0.1:8000/docs.

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=..\work\pytest-temp
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

PostgreSQL is required for real database operations and online migrations. Health/startup tests and offline Alembic validation do not require a live database. No PostgreSQL installation or SQLite fallback is provided.

## Foundation scope

The API includes health, configuration, PostgreSQL wiring, User/Session models, migrations, and shared Google authentication for web and desktop. Audio capture, microphone access, system audio, transcription, question detection, AI, meeting sessions, always-on-top behavior, and global shortcuts remain deferred. The desktop Ready label indicates that the shell is available. See `backend/README.md` and `desktop/README.md` for authentication setup and verification.

Both applications use the MeetGuide navy/white/slate/blue identity, keyboard focus styles, readable sans-serif typography, and light/dark mode. Dependencies, builds, Rust targets, generated Tauri schemas, local configuration, caches, logs, IDE files, and toolchains are ignored at the repository root.

Session preparation: `/app` saves a purpose, objective and optional explicitly selected context documents. Existing PDF/DOCX/TXT documents remain reusable; documents are not automatically used across meetings. Desktop reviews/freezes a preparation before Start, and Live Cue BM25 retrieval is restricted to that frozen selection. See backend/README.md for migration `0004_session_preparations`, privacy details and the combined later manual test plan. Live transcripts and cue cards remain session-only.
