# MeetGuide desktop companion

Separate Windows-first Tauri 2 + React + TypeScript + Vite + Tailwind application. The web application remains in `../frontend/`.

```powershell
npm install
npm run typecheck
npm run test
npm run build
npm run tauri dev
```

See the root README for Windows prerequisites and the project-local Rust toolchain, or run `../start-desktop.ps1` from PowerShell. `npm run dev` serves a browser-only preview at http://127.0.0.1:1420; authentication requires the native Tauri window. `npm run tauri build` also compiles/packages the application.

## Google authentication

Start the existing FastAPI server at http://127.0.0.1:8000 with its existing server-only Google configuration. Restart it after these backend changes. The Google Cloud redirect stays `/api/auth/google/callback` on the backend: no new Google client, desktop secret, custom URI registration, or migration is needed.

The app restores its saved session on launch. Sign in with Google opens the normal system browser. Rust binds an OS-selected port on **127.0.0.1 only** before opening the browser, generates a random state and PKCE S256 verifier, and sends only state/challenge/port to the backend login route. The existing Authlib flow verifies Google state, nonce, identity, and email.

The backend redirects a one-use handoff code (60-second expiry) and desktop state to the listener. Rust validates state, exact Host/path/method and parameter counts, exchanges the code with its verifier, then loads the user. The final opaque session token is never put in a URL or returned to React. A three-minute listener timeout and Cancel sign-in close abandoned attempts. Successful login brings the main window into focus when Windows permits it.

Rust alone calls `/api/auth/desktop/exchange`, `/me`, and `/logout`. The session uses the existing PostgreSQL users/sessions tables and TTL (seven days by default). Only token hashes are stored in PostgreSQL. Windows Credential Manager stores the desktop token under the current Windows account; it is never persisted in localStorage, a plaintext config, or the WebView cookie jar. Non-Windows secure persistence is not implemented and fails closed.

Startup revalidates the saved credential. A 401 clears it; network/server/credential-store errors retain it and offer Retry. Logout revokes the backend session **before** deleting the Windows credential. Failed revocation keeps the signed-in UI and allows retry. Web and desktop have independent sessions for the same account; desktop logout does not log out the web browser. If secure storage fails after exchange, Rust attempts to revoke the new session instead of saving it insecurely. Never enable request/response-body or authorization-header logging.

The native backend origin defaults to http://127.0.0.1:8000. A deployment may set **build-time** `MEETGUIDE_API_URL` to a trusted HTTPS origin before compiling Rust; it contains no credentials. HTTP is accepted only for numeric 127.0.0.1 development. Native HTTP follows no redirects, and errors never include request URLs, response bodies, or tokens. Avatar images may load over HTTPS; the WebView has no general backend-network or credential-store capability.

## Manual verification

1. Start the updated backend and native desktop app; sign in and confirm the system browser opens.
2. Complete Google authentication; confirm the desktop shows the same MeetGuide account, avatar/name, and Sign out. The browser receives only a short-lived handoff code.
3. Close/reopen the native app; confirm the account is restored from Windows Credential Manager and validated by the backend.
4. Sign out, then restart; confirm signed-out state. Confirm the web browser remains independently authenticated.
5. Try Cancel, let an attempt time out, and test a backend outage. Logout failure must preserve the credential for retry.

Automated backend tests mock Google and persistence (no Neon access); Rust tests cover callback validation, PKCE, transport restrictions, and a disposable Windows credential round trip; React tests mock native commands. They do not replace a real Google login/restart/logout test.

Branding, theme toggle, Ready status, and disabled Start Session remain. No audio, AI, meeting sessions, or always-on-top behavior is implemented.
