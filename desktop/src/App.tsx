import { DesktopAuth } from "./components/DesktopAuth";
import { useTheme } from "./hooks/useTheme";
export default function App() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div className="desktop-shell">
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
      <main>
        <p className="eyebrow">DESKTOP COMPANION</p>
        <h1>MeetGuide AI</h1>
        <p className="tagline">Your real-time AI meeting assistant.</p>
        <DesktopAuth />
        <section className="status-panel" aria-label="Desktop status">
          <div className="status-row">
            <span className="status-label">Application status</span>
            <span className="ready">
              <span className="status-dot" aria-hidden="true" />
              Ready
            </span>
          </div>
          <div className="session-action">
            <button
              className="start-session"
              disabled
              aria-describedby="foundation-note"
            >
              Start Session
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
              >
                <path d="M5 12h14m-5-5 5 5-5 5" />
              </svg>
            </button>
            <p id="foundation-note">
              Session controls will be available in a future update.
            </p>
          </div>
        </section>
      </main>
      <footer>
        <span>MeetGuide AI</span>
        <span>Desktop foundation</span>
      </footer>
    </div>
  );
}
