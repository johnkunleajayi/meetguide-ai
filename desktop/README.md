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

The default adapter uses Gemini 3.5 Transcribe Live; Deepgram Nova-3 remains a deliberately configured dormant alternative. Provider credentials are **backend-only**. The provider interface and normalized event contract are in `backend/app/transcription/`; changing providers does not require replacing WASAPI or the desktop transcript UI. The desktop only knows the MeetGuide relay protocol.

### Required manual provider setup

1. Confirm the existing backend-only Gemini API key has access/quota for `gemini-3.5-transcribe-live`. Never put a provider key in desktop/Vite configuration.
2. In the existing ignored `backend/.env`, manually set `TRANSCRIPTION_PROVIDER=gemini` and `GEMINI_TRANSCRIBE_MODEL=gemini-3.5-transcribe-live`; retain `TRANSCRIPTION_LANGUAGE=en-US`. Do not change Google/Neon/key values.
3. Gemini is the code default, but an existing explicit `TRANSCRIPTION_PROVIDER=deepgram` overrides it. Remove/change that value to test Gemini. Deepgram never activates automatically on failure.
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
- There is no local audio file, transcript file, PostgreSQL transcript storage, transcript logging, or offline recording. Audio now **leaves the device** via the MeetGuide relay for provider processing. The configured provider processes live audio; review its current account data-use and retention policy. Gemini uses VERBATIM output, automatic server VAD and generic technical vocabulary; local spoken-turn assembly remains unchanged. Connection renewal before the ten-minute provider limit may cause a short visible gap; stale audio is not replayed. Avoid websocket/frame debug logging and keep HTTPS/WSS outside loopback development.
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

Automated tests use synthetic PCM, a local fake WebSocket relay and mocked provider responses. They validate transport/lifecycle/source separation but do not claim real Gemini transcription accuracy. The audio-only opt-in hardware smoke test remains offline and never streams real microphone audio to a provider.

## Conversation understanding foundation

Final transcript segments feed a native in-memory engine (`src-tauri/src/understanding/`). Nearby fragments from the same source/connection assemble within a 3-second activity gap. Incomplete speech can continue; a completed request accepts linked qualifiers or follow-on questions. Ordinary new sentences and fresh commands remain separate. An intervening answer (including microphone interim speech), connection gap, new epoch or oversized turn prevents merging. Interims never become context/events and block detection while active.

Context retains at most 32 turns / 24 KB; individual turns are capped at 4 KB. Each event snapshots at most 8 recent turns / 6 KB. The event ring retains 8 events. Nothing is persisted. Start/restart resets context/events; Stop cancels processing while leaving the last session visible. Logout clears text; shutdown stops processing.

The first `UnderstandingProvider` uses conservative English question/request rules, not an LLM. Only **Them** generates questions. A 1.2-second quiet debounce, incomplete-fragment guards, minimum heuristic confidence 0.82 and a bounded 128-key normalized duplicate cache with 45-second expiry limit noise. Distinct validated questions no longer wait behind a detection cooldown; they enter the session FIFO. Confidence is rule strength, not a probability. Ambiguous/indirect questions and other languages may be missed. Connection gaps cancel pending detection.

A small **Question detected** indication shows the latest event. Reserved opportunity event types still have no suggestions. Settled uncertain requests can reach the separate backend OpenAI intent classifier; it never receives résumé excerpts or previous cue answers.

### Manual understanding check

1. Start the API and native desktop app as above, sign in and start **Both**. Use headphones to avoid microphone bleed.
2. Play system audio asking “How did you handle the Salesforce migration?” Pause at least 1.2 seconds after final text. Expect a question indication with **Them** transcript.
3. Speak a microphone reply or question. Expect **You**, without a new detected question.
4. Test “Tell me about yourself.” and “What would you do differently” from system audio, allowing over 6 seconds between questions. Expect detection without needing a question mark.
5. Test a statement and incomplete “Can you explain…”; expect no new event. Complete it naturally to check fragment merging. Continuous interim speech must not emit early.
6. Repeat a detected question (including punctuation/case changes): no new event. Two different questions in quick succession must both enter the queue. Repeat the request after the 45-second duplicate window to check that suppression is not permanent.
7. Stop: no further events, even during final transcription flush. Restart: context/indication start clean and the same question may be detected again. Logout: text/indication disappear. Close/reopen: no conversation content is restored.

Tests verify event counts/context bounds independently of the session cue feed, which retains all completed cards until Remove or session end. Real acoustic/ASR behavior requires the manual check.

## Personalized Live Cue

A sufficiently confident finalized Them question now prepares a ready-to-speak answer through the authenticated MeetGuide backend. The native layer reads the existing session credential from Windows Credential Manager; React never receives it. The workspace shows Preparing answer, then readable paragraphs and a small document-excerpt/general-approach indicator. Errors offer an explicit Retry answer button without stopping transcription.

Native session/event IDs prevent duplicate generation and mismatched results. Distinct requests enter FIFO order; they do not supersede each other. Continuations update only their related logical request. UI rendering requires the active session identity. Stop/restart/logout and window close invalidate pending native work and clear cues. No cue is stored on disk or in PostgreSQL. Cancellation is best effort after a provider has received a request.

Generation is disabled until the backend is configured. See backend/README.md, Personalized Live Cue, for exact environment variables, free-tier privacy/cost implications and safe fictional-data test steps. Do not test free-tier Gemini with a real résumé or private meeting. No desktop key or new npm/Rust dependency is required. The existing transcription/understanding path remains independent of provider failures.


## Windows beta distribution

The NSIS installer bundles the native executable and web UI. End users do not need Node, Rust, Cargo or the source tree. Windows WebView2 is required; Tauri's default installer downloads its bootstrapper when needed (internet access required).

Product: MeetGuide AI, version 0.1.0 (internal beta), stable identifier `com.meetguide.desktop`. Keep this identifier to preserve app/session identity. Existing navy/blue app icons are retained; final brand icon review remains separate.

Release builds require an explicit **build-time**, non-secret API origin:

```powershell
cd desktop
$env:MEETGUIDE_API_URL = "http://127.0.0.1:8000" # internal local-backend beta ONLY
# Use the repository-local toolchain if Rust is not on PATH:
$env:CARGO_HOME = (Resolve-Path ../work/tools/cargo).Path
$env:RUSTUP_HOME = (Resolve-Path ../work/tools/rustup).Path
$env:PATH = "$env:CARGO_HOME/bin;$env:PATH"
npm run tauri build -- --bundles nsis
```

For a customer build, replace that value with the actual deployed HTTPS API origin and rebuild. No production URL exists yet. The internal local-backend installer requires the backend on the same computer; it is not a remotely connected customer release. Debug development continues to default to 127.0.0.1:8000. All auth, transcription and cue endpoints derive from this one native origin. Never package backend environment files or provider secrets.

Before production: configure the backend Google redirect URI to its deployed HTTPS `/api/auth/google/callback` and register that exact URI with Google. Configure the deployed frontend origin and secure production cookie settings on the backend. Retain the existing ephemeral 127.0.0.1 desktop handoff; no desktop Google secret or custom redirect scheme is required. The API host must support HTTPS and transcription WebSockets (WSS).

Installer output: `src-tauri/target/release/bundle/nsis/`. This beta is unsigned: Windows may show SmartScreen and Unknown Publisher warnings. No updater or signing configuration is included. No website download link is published until a public HTTPS installer URL is selected. Manually test installation, launch, Google login, audio, transcription and Live Cue before distributing.


### Session cue flow and semantic intent

The native candidate outbox, FIFO question queue and cue-card collection are separate from bounded transcript/context rings. The UI does not drive generation or read only the newest event. One answer request executes at a time. Every distinct validated question is queued; failures do not block the following question and have an explicit Retry action.

Completed cards accumulate in memory without count/time pruning. Remove affects only that card, not audio, transcripts, conversation understanding or unrelated queued questions. Clear all is deferred. Stop, new session, logout and close reset the native collection and invalidate in-flight results. Nothing is restored on app restart. Completed requests release redundant transcript payload context. A reader scrolling older cards is not pulled away; View latest is offered for new arrivals.

Local assembly remains first (3-second merge window; 1.2-second quiet debounce). Obvious complete questions stay local. Acknowledgements, duplicate finals and You speech never trigger semantic calls. Meaningful uncertain turns, fragment assemblies, continuations and contextual follow-ups may call the authenticated backend `/api/intent/classify`. A false local result does not automatically discard meaningful speech. Native requests contain at most 1,600 candidate characters, six recent transcript turns / 4,000 characters and one eligible previous request. They contain no cue answers or Context Library documents.

OpenAI intent shares the backend OpenAI Live Cue model/key and returns ACTIONABLE_REQUEST, CONTINUATION, FOLLOW_UP or NOT_ACTIONABLE, a normalized request and confidence. Eligible continuation updates preserve one logical cue; unrelated questions cannot overwrite it. Unsent revisions coalesce; an active obsolete revision finishes without publishing stale text, then the enriched request is generated through the same gate. An existing completed answer stays readable during an update.

Semantic Intent uses the backend OpenAI key and configured Live Cue model, independently of Gemini STT. No semantic fallback to Gemini is used. Intent calls are serialized and limited to 12 per rolling minute per desktop session, with an 8-second backend / 10-second native HTTP timeout and small structured output. Disabled intent, unavailable network, quota, malformed/low-confidence output or budget exhaustion falls back to local detection and surfaces a restrained notice. Unknown semantic requests may be missed during an outage; known local questions and transcription continue. Optional `INTENT_ENABLED=false` on the backend disables semantic intent only. Do not put provider credentials in desktop configuration.

### Spoken-turn assembly check

Play “Tell me about a Salesforce integration you worked on.” followed within three seconds by “And challenges you faced.” The transcript keeps two original finals; the detected request includes both parts. The quiet debounce remains 1.2 seconds from the latest speech activity; MeetGuide does not wait out the full merge window.

If the first part was already detected, the continuation enriches the same logical request. Pending unsent work is superseded; already sent work uses the existing single-request gate and cannot publish its obsolete result. One logical card is retained for the request. A separate answer or a long pause creates a separate follow-up. Prefix and complete request fingerprints suppress immediate replay even if ASR changes segmentation; they expire after 45 seconds. Raw transcript entries are never rewritten or persisted by assembly.

### Gemini baseline manual regression

After backend restart, launch the development desktop (the existing installer is not rebuilt). Test System, Microphone and Both separately; labels remain Them and You. Using non-sensitive test material, speak each once: (A) Tell me about a Salesforce integration you worked on and challenges you faced. (B) How did you handle the Salesforce migration? (C) Tell me about yourself. (D) Tell me about a Salesforce integration you worked on... [natural pause] And challenges you faced. Compare interim/final quality, fragmentation, time to Question detected, time to Ready to speak, and distinct retained cue cards without removing prior cards. Live Cue/intent require their existing backend configuration. Verify Stop/restart/sign-out clears session state; interrupt networking then restore it to check visible reconnect gaps without stale replay. Test beyond ten minutes to observe renewal. Transcription usage should appear only in Gemini, with no Deepgram connection or audio consumption. Semantic Intent and Live Cue use OpenAI. These are manual checks, not claimed automated results.

## Development latency measurement

Use `./start-desktop.ps1` from the repository root, not the old installed beta. Native `[MeetGuide Timing]` JSON lines appear in **the PowerShell terminal running Tauri**. Backend stage lines appear in **the Uvicorn terminal**. Copy both sets of lines for the same `question_id`. Native timing logs are debug-build only; backend stage diagnostics are suppressed in production. Optional `cue_ui_observed` logs appear in the WebView development console, measuring when React first sees Ready (not GPU paint completion).

Each logical question keeps an opaque ID through Intent, FIFO queue, answer requests and its completed card. Continuation records link candidate IDs to the existing logical ID. Retries retain that ID and increment `attempt`; original detection-to-completion includes time before the retry, while queue wait and desktop request timings are per attempt. Session question index and session age are captured at enqueue. Conversation, queue and cue retention behavior are unchanged.

`assembly_wait_ms` measures actual wait from the latest contributing native final to local candidate analysis, alongside the unchanged configured 1200 ms quiet debounce and separate local detector CPU time. `native_final_to_question_detected_ms` includes semantic routing/backlog where used; `final_transcript_to_ready_ms` begins at that native final, not at physical speech onset or backend Gemini receipt. Backend STT final-emission and native receipt records can be joined by stream ID/source/segment; do not treat cross-process wall-clock subtraction as precise one-way latency. Backend generation, retrieval and validation use monotonic timers; no private content is logged.

Small manual baseline: restart the backend and development desktop, sign in, choose Both and Start Session. Speak Q1 "Tell me about yourself."; Q2 "Tell me about a Salesforce integration you worked on and the challenges you faced."; then the context statement "Our Salesforce implementation was completed last year." followed by Q3 "If you joined our company, what would you do differently?"; finally Q4 "Why should we hire you?". Let each answer finish to compare provider timing, or explicitly note any overlapping questions when examining queue wait. Keep cue cards. Copy only `[MeetGuide Timing]` lines from the two terminals, including `backend_live_cue`, `queue_processing_started`, `cue_ready` (or `cue_failed`) and Intent records. If an answer fails, Retry once and keep both attempts' lines. Stop afterward. No installer rebuild or real-provider automated test is required.


## Prepared sessions

Create/save a preparation in the web workspace, then refresh preparations in desktop. Review its purpose, objective and selected-document count; a no-document preparation is supported. Start Session requires a selected preparation. Native Start freezes the reviewed revision using the authenticated backend; stale revisions require refresh. Selection controls are hidden while starting/listening. The frozen signed scope stays in Rust memory, is copied to each cue request and is cleared on Stop/logout/restart. Editing or activating another web preparation changes the next session only. Deleting an actual document still removes its availability immediately. A frozen scope expires after 12 hours; start a new session then. Backend `0004_session_preparations` must be applied before manual use. The installed beta is unchanged; use the development app for later verification.

WASAPI, Gemini transcription, source mapping, Intent, FIFO cue feed, Remove/Retry and content-free timing diagnostics are preserved. No provider key, live snapshot or session token is added to desktop JavaScript or persisted with cue/transcript state. See the backend README for the combined later manual plan and migration command.


## Streaming Live Cues

The desktop requests authenticated NDJSON from the existing cue endpoint. Rust reconstructs bounded frames, checks question IDs/attempts and pushes `meetguide-cue-update` to the local main window. React reads one initial snapshot and then uses events, without polling Live Cues. Only local listen/unlisten permissions are added; JavaScript does not receive provider keys or native session tokens.

Cards progress through Queued → Preparing answer → Responding (draft) → Ready to speak, or Answer unavailable. Provisional text is clearly labelled as awaiting final grounding checks. Failure clears partial text. Retry retains the question ID, increments the attempt and starts empty. Removing a responding card hides it while generation continues invisibly and retains its FIFO slot until completion/failure. Stop/logout resets state and cancels pending native work. Completed cards are retained for the active session without automatic pruning.

Restart the native development app after updating its event permissions. For a later real test, review the same preparation, start a fresh Both-mode session and ask “Tell me about yourself” once. Draft sentences should appear before Ready to speak. Then check queued questions, Remove during Responding and Retry after any transient failure. Compare backend/native `[MeetGuide Timing]` logs and the WebView's development console by question ID and attempt. New metrics measure first useful output separately from full completion; no real-provider speedup is claimed from mocked tests.

See [backend streaming documentation](../backend/README.md#streaming-live-cues) for protocol, provisional safety limits, unchanged model/prompt/context and the existing 25-second HTTP / shared 27-second generation / 35-second native timeout boundaries. No migrations, installer rebuild, new provider credentials or new dependencies are required.

## Private Display (Windows)

Private Display starts ON when the native main window opens, including before a live
session. It calls `SetWindowDisplayAffinity` on Tauri's top-level HWND with
`WDA_EXCLUDEFROMCAPTURE` (`0x11`); OFF uses `WDA_NONE` (`0`). Every operation reads
`GetWindowDisplayAffinity` back. ON means Windows confirmed that affinity flag, not
that every capture tool is guaranteed to respect it. Rejected calls, limited affinity
and unreadable state are shown honestly; Check status refreshes the native read-back.
Only two commands are exposed to the local main-window capability.

The choice lives in Rust for the current application run, independently of audio,
authentication, preparations, transcripts and cues. Stop/logout/React reload do not
silently turn protection off or override an explicit OFF choice. Focus/restore checks
and repairs the requested setting; resizing retains the same HWND/affinity. Closing
destroys the window and Windows removes its per-window affinity automatically. No
global Windows capture setting or persistent preference is written. Relaunch defaults
to ON. The app is never hidden, minimized or made transparent by this feature.

True capture exclusion needs Windows 10 version 2004 or newer and a composing DWM.
Older Windows versions may show a blank window instead. Capture paths vary by tool,
OS, driver and remote-session environment; this is not DRM, universal invisibility or
a guarantee against capture. It cannot prevent a camera photographing the screen.
Only the main MeetGuide window is covered, not separate developer tools, system
dialogs, browser windows or other applications. Non-Windows reports Unavailable.
Microsoft references:
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity
and
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowdisplayaffinity .

Later manual check (use the updated development app, not the unchanged installer):

1. Run `./start-desktop.ps1` from the repository root. Confirm Private Display: ON
   locally; test Check status, resize, minimize/restore and focus changes.
2. Put non-sensitive sample content behind MeetGuide and use Windows Snipping Tool
   (Win+Shift+S) to capture a region containing the window or the whole screen. Inspect
   the resulting image: MeetGuide should be excluded on a supported path while it
   remains visible on your monitor.
3. Turn OFF and repeat the same capture: MeetGuide should now appear. Turn ON and
   repeat. Do not rely on the toggle alone as proof for a particular capture tool.
4. Share the entire monitor in your actual Teams/Zoom/Meet setup with a second
   device/recipient. Verify the recipient's view with ON and OFF; sharing an unrelated
   browser tab does not test this feature. Record any unsupported behavior.
5. Confirm Start/Stop still works and toggling does not stop an active session.
   An optional existing live session may be used later; no provider call is needed for
   the screenshot checks. An explicit OFF choice survives Stop/new session in the same
   app run. Close/relaunch and confirm the default returns to ON.

No backend, provider, database, installer or updater changes are involved.


## Code Assist

Code Assist uses the existing FIFO Live Cue feed and OpenAI streaming endpoint. Clear local
programming requests bypass semantic Intent; uncertain normal speech keeps the existing
Intent route. Code cards show the problem, language, Approach, formatted Code, optional
Complexity and What to say. They transition Queued / Preparing / Responding (Draft) / Ready
or the existing retryable error. Code is displayed as escaped React text in a keyboard-
scrollable `pre/code` block, never HTML, clipboard automation or executable input.

One bounded coding problem and its last validated solution are kept separately from the
visible feed. Coding follow-ups create new cards; a queued follow-up can use the solution
that finishes before its FIFO slot. Remove never erases this context or releases an active
slot. A normal actionable question ends the coding chain; a new session/Stop/logout clears
all coding memory. Retry keeps the question ID, increments the attempt and clears partial
code. Preparation scope, source separation and latency diagnostics stay intact.

Web Job Interview preparation may optionally indicate Technical/Coding interview and a
preferred language. Desktop review shows it; the existing signed preparation freeze carries
it to the backend. Explicit spoken language takes priority. Auto and all supported language
preferences are documented in the backend README. Existing preparations remain valid.
Backend migration `0005_code_assist_preference` is pending and must be reviewed/applied
manually before live use of the updated preparation API. No provider configuration change,
Private Display change or installer rebuild was performed. Use the development app for the
combined later manual test in the backend README. Automated tests mock providers; generated
code correctness and real-world recognition still require manual review.
