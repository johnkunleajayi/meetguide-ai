import { useState } from "react";
import { AudioSession } from "./components/AudioSession";
import { DesktopAuth } from "./components/DesktopAuth";

import { useTheme } from "./hooks/useTheme";
export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [authenticated, setAuthenticated] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);
  return (
    <div className="desktop-shell" data-authenticated={authenticated}>
      <a className="skip-link" href="#main">Skip to conversation workspace</a>
      <header className="shell-header">
        <span className="wordmark">
          <svg
            width="25"
            height="25"
            viewBox="0 0 40 40"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M12 17v6m8-12v18m8-12v6"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </svg>
          MeetGuide <span>AI</span>
        </span>
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? (
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
            </svg>
          ) : (
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <path d="M20 15.3A8.5 8.5 0 0 1 8.7 4a8.5 8.5 0 1 0 11.3 11.3Z" />
            </svg>
          )}
        </button>
      </header>
      <div className="account-toolbar"><span>DESKTOP COMPANION</span><DesktopAuth onAuthenticatedChange={setAuthenticated} sessionBusy={sessionBusy} /></div>
      <main id="main" tabIndex={-1}>
        {!authenticated && <section className="welcome-panel"><p className="eyebrow">PREPARE ON THE WEB. BE PRESENT HERE.</p><h1>Your conversation,<br />with context.</h1><p>Your real-time AI meeting assistant.</p><span>Sign in with the same account you use in your web workspace. Review your preparation, then start when you're ready.</span></section>}
        <AudioSession authenticated={authenticated} onBusyChange={setSessionBusy} />
      </main>
      <footer>
        <span>MeetGuide AI</span>
        <span>Live conversation stays session-only</span>
      </footer>
    </div>
  );
}
