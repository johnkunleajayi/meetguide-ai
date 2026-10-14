# MeetGuide AI

**Your real-time AI meeting assistant.**

## Architecture

```text
meetguide-ai/
├── frontend/     MeetGuide web application
├── desktop/      MeetGuide desktop companion
├── backend/      MeetGuide API (empty placeholder)
├── .gitignore
└── README.md
```

A single Git repository at the project root contains three independent applications:

- `frontend/`: the existing React + TypeScript + Vite + Tailwind web application. The roadmap includes the marketing website, signup/login, dashboard, AI provider connections, documents/context, session preparation, account/settings, and desktop downloads. Currently only the verified marketing frontend is implemented.
- `desktop/`: a separate Windows-first Tauri 2 + React + TypeScript + Vite + Tailwind companion for use during meetings. Currently only a minimal shell is implemented: brand, tagline, Ready status, theme toggle, and a disabled Start Session button.
- `backend/`: reserved for the shared FastAPI + PostgreSQL API for web and desktop. It contains only `.gitkeep`; FastAPI and database code have not been created.

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

The web source and existing visual design are preserved. Web preview conversations and cues are static examples.

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

- `desktop/src/App.tsx`: minimal shell with no session behavior.
- `desktop/src/hooks/useTheme.ts`: system-aware light/dark mode with optional stored preference.
- `desktop/src/styles.css`: navy/slate/blue visual tokens and responsive shell styling.
- `desktop/src-tauri/`: native window configuration and minimal Rust bootstrap.
- `desktop/src-tauri/capabilities/default.json`: no privileged API permissions.
- `desktop/src-tauri/icons/`: branded native application icons.

## Foundation scope

No backend, authentication, API connections, database, session logic, audio capture, microphone access, system audio, transcription, question detection, AI, always-on-top behavior, or global shortcuts are implemented. The desktop Ready label means the shell is available, not that those capabilities are connected.

Both applications use the MeetGuide navy/white/slate/blue identity, keyboard focus styles, readable sans-serif typography, and light/dark mode. Dependencies, builds, Rust targets, generated Tauri schemas, local configuration, caches, logs, IDE files, and toolchains are ignored at the repository root.
