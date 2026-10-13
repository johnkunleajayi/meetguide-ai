# LiveCue AI

A responsive frontend foundation for a real-time conversation copilot.

**Hear it. Understand it. Know what to say.**

## Local setup

Requires Node.js 22.12+ (or 24 LTS) and npm.

```powershell
cd C:\Users\JOHN-KUNLE\OneDrive\Desktop\livecue-ai
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite (normally http://127.0.0.1:5173).

```powershell
npm run typecheck
npm run build
npm run preview
```

## Structure

- `frontend/`: complete React, TypeScript, Vite, and Tailwind application.
- `backend/`: empty placeholder; no backend code yet.
- Root `.gitignore`, `README.md`, and `.git/`: repository-level files.

Frontend files:

- `frontend/src/App.tsx`: landing page composition.
- `frontend/src/components/ui.tsx`: brand, button links, and section labels.
- `frontend/src/components/LiveCuePreview.tsx`: static Salesforce interview workspace preview.
- `frontend/src/components/ContextSection.tsx`: illustrative knowledge-to-cue diagram.
- `frontend/src/hooks/useTheme.ts`: system-aware light/dark mode with a saved preference.
- `frontend/src/data/workflow.ts`: authored workflow content.
- `frontend/src/styles.css`: Tailwind entry, semantic color tokens, reusable visual styles, responsive rules.
- `frontend/public/favicon.svg`: local vector brand mark.

React + TypeScript + Vite + Tailwind CSS (Vite plugin). Lucide supplies consistent SVG icons. No external font or image requests are required. Theme initialization runs before React to avoid a theme flash. Theme storage is optional and gracefully falls back when unavailable.

## Scope

This is a frontend concept only. The workspace, transcript, timer, and cues are static examples. No backend, authentication, database, audio capture, transcription, or AI is implemented. CTAs navigate to sections; there is no signup flow. Sign in is disabled with an explanatory tooltip. The listening status and interview cue are illustrative. No microphone permissions are requested.

## Visual system

Semantic CSS variables define surfaces, ink, muted text, borders, accents, and shadows for both themes. Tailwind theme tokens establish the sans font, accent, and card radius. The page uses professional sans-serif typography, the specified navy/slate/blue palette, thin borders, restrained corners, a horizontal workflow, and an understated contextual-intelligence diagram. Dark surfaces are intentionally layered in deep navy, primary navy, and surface navy. Green is reserved for the listening indicator. Includes keyboard focus styles, skip navigation, semantic landmarks, labeled theme controls, and reduced-motion support.
