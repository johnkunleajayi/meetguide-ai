import { AudioLines, FileText, LayoutGrid, Monitor } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { AuthControlsWithState } from "../components/AuthControls";
import { Brand } from "../components/ui";
import { ThemeToggle } from "../components/ThemeToggle";
import type { useAuth } from "../hooks/useAuth";
import "../workspace.css";
export function WorkspaceLayout({ auth }: { auth: ReturnType<typeof useAuth> }) {
  return <div className="workspace-shell"><a className="skip-link" href="#main">Skip to content</a><header className="ws-topbar"><div className="ws-app-brand"><Brand /><span>PREPARATION WORKSPACE</span></div><div className="header-actions"><ThemeToggle /><AuthControlsWithState auth={auth} /></div></header><div className="ws-workspace-layout"><aside className="ws-sidebar"><nav className="ws-navigation" aria-label="Workspace navigation"><NavLink to="/app" end aria-label="Preparation"><LayoutGrid size={17} strokeWidth={1.5} /><span>Preparation</span></NavLink>{auth.state.status === "authenticated" && <><a href="#context-library" aria-label="Relevant context"><FileText size={17} strokeWidth={1.5} /><span>Context</span></a><a href="#desktop-companion" aria-label="Desktop companion"><Monitor size={17} strokeWidth={1.5} /><span>Desktop</span></a></>}</nav><div className="ws-sidebar-note"><AudioLines size={24} /><span>Prepare.<br />Be present.</span></div></aside><main id="main" tabIndex={-1} className="ws-main"><Outlet /></main></div></div>;
}
