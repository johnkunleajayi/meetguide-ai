import { PreparationEditor } from "../components/workspace/PreparationEditor";
import { DesktopCompanion } from "../components/workspace/DesktopCompanion";
import { useContextLibrary } from "../hooks/useContextLibrary";
import type { AuthUser } from "../lib/auth";
export function WorkspacePage({ user }: { user: AuthUser }) {
  const library = useContextLibrary();
  const firstName = user.name?.trim().split(/\s+/)[0];
  return <div className="ws-page"><section className="ws-welcome" aria-labelledby="workspace-title"><div><p className="ws-eyebrow">A CLEARER CONVERSATION STARTS HERE.</p><h1 id="workspace-title">Welcome back{firstName ? `, ${firstName}` : ""}.</h1><p>Make a little room for preparation.<br />Bring your best to what comes next.</p></div><div className="ws-welcome-note"><span>YOUR PREPARATION SPACE</span><p>Set the direction here.<br />MeetGuide Desktop takes it live.</p></div></section><PreparationEditor library={library} /><DesktopCompanion /><p className="ws-page-footnote">Your preparation persists. Your live conversation stays session-only.</p></div>;
}
