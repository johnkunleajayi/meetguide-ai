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

Branding and the theme toggle remain. Authenticated users can now start local Windows audio capture as described below. No transcription, AI, audio uploads, meeting recordings, or always-on-top behavior is implemented.

## Live Windows audio capture

Use **System Audio**, **Microphone**, or **Both**, then choose Windows-default or specific active devices. Start Session is enabled only after authentication and device discovery. Native startup reuses existing backend session validation; no audio is sent with that request. The existing backend must therefore be reachable when starting a new capture.

Rust uses WASAPI shared mode. System Audio captures the selected playback endpoint's mix using Windows loopback; it does not depend on Stereo Mix or browser screen sharing. Microphone uses a capture endpoint. Both keeps the streams separate, without mixing, synchronizing, resampling between streams, echo cancellation, or speech processing. Windows supplies each endpoint's native sample rate/channel count; shared-mode format conversion requests interleaved float32 PCM.

COM clients live entirely on one dedicated worker thread. Driver packets are borrowed only until release and synchronously consumed by a small in-memory level accumulator. Silent packets (including null pointers) are handled explicitly. There is no audio file, PCM backlog, IPC audio payload, network upload, or raw-audio logging. The frame-consumer boundary in `src-tauri/src/audio/meter.rs` is the extension point for a later, separately scoped transcription milestone.

The worker drains packets every ~10 ms and publishes RMS/peak aggregates about every 100 ms. The UI shows one RMS activity meter per selected source using a -60 to 0 dBFS display range. Quiet intervals return the meter to zero. Device name, native sample rate and channel count are displayed; sample/frame counts and discontinuity totals are metadata only.

Stop Session signals and joins the worker, releasing all streams and resetting activity. Logout and main-window close also stop capture. Start/stop/logout are serialized, including session validation, to avoid starting a new capture during logout. Both-mode startup is all-or-nothing: failure or loss of either endpoint releases both streams. Startup failures, microphone permissions, endpoint removal and stream errors produce retryable messages. Selected defaults are checked every ~500 ms; a default-device change stops the session instead of silently switching devices. Refresh devices and restart after a change. Device selection is locked during capture.

Loopback covers audio played **through the selected endpoint**, including other applications; select the actual headset/speakers used by the meeting. Protected content and applications taking exclusive control can prevent loopback capture. Silence is normal while no application is rendering audio. The mode does not isolate one meeting process.

### Manual hardware verification

1. Keep the existing backend running, then launch the native app from the repository root with `./start-desktop.ps1`. Sign in. A browser-only Vite preview cannot access native capture.
2. Open Windows Settings > System > Sound. Confirm the intended playback device and microphone are active. In Privacy & security > Microphone, enable microphone access and desktop app access.
3. Select **System Audio** and the endpoint playing a YouTube video or meeting. Click **Start Session**. Expect **Listening**, an activity meter and device metadata. Play/pause audio: activity should rise/fall. Click **Stop Session**; expect **Ready** and cleared meters.
4. Select **Microphone**, choose Windows default or a specific microphone, and start. Speak or tap near it; activity should respond. Stop and restart to verify the device is released and reusable.
5. Select **Both**. Use headphones to make the sources easy to distinguish. Play audio and speak: both independent meters should respond. Stop, then start again.
6. While capturing, unplug/disable a selected USB device, or change a selected Windows-default endpoint. Expect capture to stop with an actionable error. In Both, both streams must stop. Reconnect, click **Refresh devices**, reselect if necessary and restart.
7. Disable microphone access in Windows and try Microphone/Both. Expect a startup error without a Listening state. Restore access, refresh and retry. With no active playback device, System Audio/Both must not silently fall back to microphone.
8. Sign out while listening: capture should stop. Sign back in and restart. Close the native window during capture and reopen it: it should start at Ready, without resuming capture automatically.
9. Confirm light/dark mode and narrow-window controls remain usable. No audio recording should appear in the project and no audio should be uploaded.

Automated checks: `npm run typecheck`, `npm run build`, `npm run test`; with the root README's Rust environment active, `cargo check --manifest-path src-tauri/Cargo.toml` and `cargo test --manifest-path src-tauri/Cargo.toml --lib` from `desktop/`. The opt-in hardware smoke test briefly opens the real default endpoints in all three modes and releases them: `cargo test --manifest-path src-tauri/Cargo.toml --lib windows_hardware_capture_smoke -- --ignored`. It never saves/uploads audio; it does not replace the audible-source, unplug, permission and UI checks above.
