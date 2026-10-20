import { AudioLines, FileText, LayoutGrid, Monitor } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { AuthControlsWithState } from "../components/AuthControls";
import { Brand } from "../components/ui";
import { ThemeToggle } from "../components/ThemeToggle";
import type { useAuth } from "../hooks/useAuth";
import "../workspace.css";

export function WorkspaceLayout({ auth }: { auth: ReturnType<typeof useAuth> }) {
  return <div className="workspace-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="ws-sidebar">
      <div className="ws-sidebar-brand"><Brand /><span className="ws-sidebar-caption">PERSONAL WORKSPACE</span></div>
      <nav className="ws-navigation" aria-label="Workspace navigation">
        <NavLink to="/app" end aria-label="Preparation" title="Preparation"><LayoutGrid size={17} strokeWidth={1.5} aria-hidden="true" /><span className="ws-nav-label">Preparation</span></NavLink>
        {auth.state.status === "authenticated" && <><a href="#context-library" aria-label="Relevant context" title="Relevant context"><FileText size={17} strokeWidth={1.5} aria-hidden="true" /><span className="ws-nav-label">Context</span></a><a href="#desktop-companion" aria-label="Desktop companion" title="Desktop companion"><Monitor size={17} strokeWidth={1.5} aria-hidden="true" /><span className="ws-nav-label">Desktop</span></a></>}
      </nav>
      <div className="ws-sidebar-note"><AudioLines size={21} strokeWidth={1.4} aria-hidden="true" /><strong>Make the moment yours.</strong><p>Prepare your conversation here.<br />Bring it to MeetGuide Desktop.</p></div>
    </aside>
    <div className="ws-content"><header className="ws-topbar"><div className="ws-breadcrumb">Workspace<span>/</span><strong>Preparation</strong></div><div className="header-actions"><ThemeToggle /><AuthControlsWithState auth={auth} /></div></header>
      <main id="main" tabIndex={-1} className="ws-main"><Outlet /></main>
    </div>
  </div>;
}
