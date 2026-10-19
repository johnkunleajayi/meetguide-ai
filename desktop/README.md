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

Branding and the theme toggle remain. Authenticated users can now start local Windows audio capture as described below. Streaming transcription is described below. AI, meeting recordings, and always-on-top behavior remain deferred.

## Live Windows audio capture

Use **System Audio**, **Microphone**, or **Both**, then choose Windows-default or specific active devices. Start Session is enabled only after authentication and device discovery. Native startup reuses existing backend session validation; no audio is sent with that request. The existing backend must therefore be reachable when starting a new capture.

Rust uses WASAPI shared mode. System Audio captures the selected playback endpoint's mix using Windows loopback; it does not depend on Stereo Mix or browser screen sharing. Microphone uses a capture endpoint. Both keeps the streams separate, without mixing, synchronizing, resampling between streams, echo cancellation, or speech processing. Windows supplies each endpoint's native sample rate/channel count; shared-mode format conversion requests interleaved float32 PCM.

COM clients live entirely on one dedicated worker thread. Driver packets are borrowed only until release and synchronously consumed by a small in-memory level accumulator. Silent packets (including null pointers) are handled explicitly. There is no audio file, unbounded PCM backlog, IPC audio payload, or raw-audio logging. Streaming transcription sends audio through the authenticated relay described below. The frame-consumer boundary in `src-tauri/src/audio/meter.rs` is the extension point for a later, separately scoped transcription milestone.

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
9. Confirm light/dark mode and narrow-window controls remain usable. No audio recording should appear in the project. Audio network traffic is limited to the configured live transcription relay.

Automated checks: `npm run typecheck`, `npm run build`, `npm run test`; with the root README's Rust environment active, `cargo check --manifest-path src-tauri/Cargo.toml` and `cargo test --manifest-path src-tauri/Cargo.toml --lib` from `desktop/`. The opt-in hardware smoke test briefly opens the real default endpoints in all three modes and releases them: `cargo test --manifest-path src-tauri/Cargo.toml --lib windows_hardware_capture_smoke -- --ignored`. It never saves/uploads audio; it does not replace the audible-source, unplug, permission and UI checks above.

## Live streaming transcription

The current Start Session flow includes live transcription. Existing WASAPI capture stays native, with independent system and microphone streams. Each is downmixed separately and resampled with an anti-aliased streaming sinc filter to 16 kHz mono PCM16, then sent in 20 ms packets to the authenticated MeetGuide relay. System Audio is labeled **Them**; Microphone is **You**. These labels identify the source, not speaker diarization (system output can contain several meeting participants).

The first adapter uses Deepgram Nova-3 Listen v1. Provider credentials are **backend-only**. The provider interface and normalized event contract are in `backend/app/transcription/`; changing providers does not require replacing WASAPI or the desktop transcript UI. The desktop only knows the MeetGuide relay protocol.

### Required manual provider setup

1. Create a Deepgram account/project and a key authorized for Speech-to-Text streaming. Ensure the account has sufficient quota/credit and access to Nova-3.
2. Add `DEEPGRAM_API_KEY=<your-real-key>` to the existing **untracked** `backend/.env`. Do not replace the file or change Neon/Google values. Do not put this key in a Vite variable, desktop source, command-line argument, or Git.
3. Defaults are `TRANSCRIPTION_PROVIDER=deepgram`, `TRANSCRIPTION_MODEL=nova-3`, `TRANSCRIPTION_LANGUAGE=en-US`. Optional backend environment overrides can change model/language. Leave the defaults initially.
4. Install updated backend requirements and restart the API from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --ws websockets-sansio --ws-max-size 8192 --ws-max-queue 8 --no-access-log --log-level warning
```

5. Start the native desktop app using `./start-desktop.ps1` from the repository root. Existing Google authentication and the backend session cookie/bearer account system are unchanged.

Missing/invalid provider configuration is shown in the transcript panel; audio capture continues safely. Do not add placeholder transcripts or interpret a working meter as successful speech recognition.

### Lifecycle, privacy and limits

- Start creates clean transcript state and one relay connection per selected source. Interims update in place; finals become immutable entries. Both mode never mixes source audio or text. The panel follows new text unless scrolled up; Follow latest resumes it.
- Stop first ends capture, sends a short conversion tail, drains bounded queued audio and requests final results with a bounded two-second grace period. Late/missing partials are marked Interrupted. A restart clears the preceding session. Logout/window close stop streams; logout clears transcript state even if backend logout later fails.
- There is no local audio file, transcript file, PostgreSQL transcript storage, transcript logging, or offline recording. Audio now **leaves the device** via the MeetGuide relay for provider processing. Provider requests set `mip_opt_out=true`; see Deepgram's current data-retention policy and verify this flag in provider request metadata. Avoid websocket/frame debug logging and keep HTTPS/WSS outside loopback development.
- Capture never waits for network I/O. Each stream queue is capped at 50 packets (~one second). On overload or disconnect, unsent audio is discarded, the gap is shown, and a fresh connection is attempted with backoff up to 15 seconds. Lost speech is not reconstructed or silently replayed. Terminal key/account/session errors require configuration/sign-in and a new session.
- During silence, realtime zero packets allow endpointing; backend keepalives preserve idle connections. Backend sessions are revalidated at least every 60 seconds with short-lived DB transactions. No database connection is held open during provider processing.
- Transcript history is session-local and bounded to the latest 200 entries / 64 KiB of text. Older entries are discarded with a visible notice. This is not meeting memory or an export/archive. Timings/order are approximate across independently connected sources. Real provider accuracy, latency and long-meeting performance require live evaluation.

### Exact live transcription test

1. Complete provider setup and restart both API and desktop. Sign in. Use a stable internet connection and headphones.
2. Choose System Audio and the playback endpoint used by a spoken YouTube clip or meeting. Start Session. Expect Listening and **Them · streaming**; spoken words should appear as Them, update while spoken and finalize after pauses.
3. Stop, switch to Microphone, start and speak several sentences. Expect **You · streaming** and You entries. No preceding-session text should remain.
4. Stop and select Both. Play speech while speaking into the chosen microphone. Confirm separate Them and You entries. Listen with headphones so speaker playback is not acoustically recaptured by the mic.
5. Scroll upward while text arrives; the panel should stay in place. Click Follow latest to resume following.
6. Stop mid-sentence. Confirm connections stop and available final results arrive; any unfinished partial is marked Interrupted. Start again and confirm a clean transcript.
7. Temporarily stop the API or disconnect networking. Capture must not crash; connection/gap state must appear. Restore connectivity and verify reconnection and new text without an offline backlog. Speech during the outage will be missing.
8. Sign out during capture, then sign in again. Confirm capture/transcription stopped and old text was cleared. Test native window close/reopen as well.
9. Run a 30+ minute meeting to evaluate real latency, accuracy, endpoint selection and stable resource use. The bounded recent-history notice is expected during sufficiently long conversations.

Automated tests use synthetic PCM, a local fake WebSocket relay and mocked provider responses. They validate transport/lifecycle/source separation but do not claim real Deepgram transcription accuracy. The audio-only opt-in hardware smoke test remains offline and never streams real microphone audio to a provider.

## Conversation understanding foundation

Final transcript segments feed a native in-memory engine (`src-tauri/src/understanding/`). Nearby fragments from the same source/connection merge (up to a 3-second activity gap); an intervening source, connection gap or oversized turn starts a new turn. Interims never become context/events and block detection while active.

Context retains at most 32 turns / 24 KB; individual turns are capped at 4 KB. Each event snapshots at most 8 recent turns / 6 KB. The event ring retains 8 events. Nothing is persisted. Start/restart resets context/events; Stop cancels processing while leaving the last session visible. Logout clears text; shutdown stops processing.

The first `UnderstandingProvider` uses conservative English question/request rules, not an LLM. Only **Them** generates questions. A 1.2-second quiet debounce, incomplete-fragment guards, minimum heuristic confidence 0.82, 6-second cooldown and bounded 128-question normalized duplicate cache limit noise. Confidence is rule strength, not a probability. Ambiguous/indirect questions and other languages may be missed. Connection gaps cancel pending detection.

A small **Question detected** indication shows the latest event. Reserved event types have no detectors or suggestions. No AI client, answers, summaries or new external calls are involved.

### Manual understanding check

1. Start the API and native desktop app as above, sign in and start **Both**. Use headphones to avoid microphone bleed.
2. Play system audio asking “How did you handle the Salesforce migration?” Pause at least 1.2 seconds after final text. Expect a question indication with **Them** transcript.
3. Speak a microphone reply or question. Expect **You**, without a new detected question.
4. Test “Tell me about yourself.” and “What would you do differently” from system audio, allowing over 6 seconds between questions. Expect detection without needing a question mark.
5. Test a statement and incomplete “Can you explain…”; expect no new event. Complete it naturally to check fragment merging. Continuous interim speech must not emit early.
6. Repeat a detected question (including punctuation/case changes): no new event. Two different questions within 6 seconds: the second is deliberately suppressed.
7. Stop: no further events, even during final transcription flush. Restart: context/indication start clean and the same question may be detected again. Logout: text/indication disappear. Close/reopen: no conversation content is restored.

Tests verify event counts/context bounds; the UI shows only the latest question, not event history. Real acoustic/ASR behavior requires the manual check.
