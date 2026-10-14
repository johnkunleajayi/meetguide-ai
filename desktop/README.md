# MeetGuide desktop companion

This is the separate Windows-first Tauri 2 + React + TypeScript + Vite + Tailwind application. The web application remains in `../frontend/`.

```powershell
npm install
npm run typecheck
npm run build
npm run tauri dev
```

See the root README for Windows prerequisites and activation of the project-local Rust toolchain. `npm run dev` opens only the browser version at http://127.0.0.1:1420. `npm run build` verifies and builds the React shell; `npm run tauri build` additionally compiles and packages the native application.

The shell shows the brand, tagline, Ready status, and a disabled Start Session button. Light/dark mode follows the system until a preference is selected. No sessions, privileged Tauri commands, plugins, audio, AI, authentication, networking, shortcuts, or always-on-top behavior are implemented.
