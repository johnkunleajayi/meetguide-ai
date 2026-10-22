import { useEffect, useState } from "react";
import { Menu, Pause, Play, X } from "lucide-react";
import { Link, Outlet } from "react-router-dom";
import { Brand } from "../components/ui";
import { ThemeToggle } from "../components/ThemeToggle";
import { AuthControlsWithState } from "../components/AuthControls";
import { LandingMotion, useLandingMotion } from "../components/landing/motion";
import { GOOGLE_LOGIN_URL, rememberWorkspace } from "../lib/auth";
import type { useAuth } from "../hooks/useAuth";
import "../landing.css";

function PublicShell({ auth }: { auth: ReturnType<typeof useAuth> }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const { paused, reduced, toggle } = useLandingMotion();
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 24);
    update(); window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="public-header-shell" data-scrolled={scrolled}>
      <div className="public-header mg-container"><Brand />
        <button className="public-menu-toggle" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="public-navigation" onClick={() => setMenuOpen(value => !value)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
        <nav id="public-navigation" className="public-navigation" data-open={menuOpen} aria-label="Main navigation" onClick={() => setMenuOpen(false)}>
          <a href="#product">Product</a><a href="#how-it-works">How it works</a><a href="#use-cases">Use cases</a><a href="#code-assist">Code Assist</a><a href="#privacy">Privacy</a>
        </nav>
        <div className="mg-header-actions"><ThemeToggle />
          {auth.state.status === "unauthenticated" ? <><a className="mg-sign-in" href={GOOGLE_LOGIN_URL} onClick={rememberWorkspace}>Sign in</a><a className="mg-button mg-header-cta" href={GOOGLE_LOGIN_URL} onClick={rememberWorkspace}>Get MeetGuide</a></> : <AuthControlsWithState auth={auth} publicSite />}
        </div>
      </div>
    </header>
    <main id="main" tabIndex={-1}><Outlet /></main>
    <footer className="public-footer mg-dark"><div className="mg-container"><div><Brand /><p>Your real-time AI meeting assistant.</p></div><nav aria-label="Footer navigation"><a href="#how-it-works">How it works</a><a href="#privacy">Privacy</a><Link to="/app">Workspace</Link></nav><span>© {new Date().getFullYear()} MeetGuide AI</span></div></footer>
    <button className="mg-motion-control" onClick={toggle} disabled={reduced} aria-label={reduced ? "Animations off: reduced motion" : paused ? "Resume animations" : "Pause animations"} aria-pressed={paused || reduced}>{paused || reduced ? <Play size={13} /> : <Pause size={13} />}<span>{reduced ? "Reduced motion" : paused ? "Motion paused" : "Pause motion"}</span></button>
  </>;
}
export function PublicLayout({ auth }: { auth: ReturnType<typeof useAuth> }) {
  return <LandingMotion><PublicShell auth={auth} /></LandingMotion>;
}
