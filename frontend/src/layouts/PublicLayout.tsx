import { useState } from "react";
import { Menu, X } from "lucide-react";
import { Outlet } from "react-router-dom";
import { AuthControlsWithState } from "../components/AuthControls";
import { Brand } from "../components/ui";
import { ThemeToggle } from "../components/ThemeToggle";
import type { useAuth } from "../hooks/useAuth";
import "../landing.css";

export function PublicLayout({ auth }: { auth: ReturnType<typeof useAuth> }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return <div className="public-site">
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="public-header-shell">
      <div className="public-header marketing-container">
        <Brand />
        <button className="public-menu-toggle" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="public-navigation" onClick={() => setMenuOpen(value => !value)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
        <nav id="public-navigation" className="public-navigation" data-open={menuOpen} aria-label="Main navigation" onClick={() => setMenuOpen(false)}>
          <a href="#demo">How it works</a><a href="#your-context">Your context</a><a href="#use-cases">Use cases</a><a href="#privacy">Privacy</a>
        </nav>
        <div className="header-actions"><ThemeToggle /><AuthControlsWithState auth={auth} publicSite /></div>
      </div>
    </header>
    <main id="main" tabIndex={-1}><Outlet /></main>
    <footer className="public-footer marketing-container"><div><Brand /><p>Your real-time AI meeting assistant.</p></div><nav aria-label="Footer navigation"><a href="#demo">How it works</a><a href="#privacy">Privacy</a><a href="/app">Workspace</a></nav><span>© {new Date().getFullYear()} MeetGuide AI</span></footer>
  </div>;
}
