import { ArrowUpRight } from "lucide-react";
import { PreparationEditor } from "../components/workspace/PreparationEditor";
import { DesktopCompanion } from "../components/workspace/DesktopCompanion";
import { useContextLibrary } from "../hooks/useContextLibrary";
import type { AuthUser } from "../lib/auth";

export function WorkspacePage({ user }: { user: AuthUser }) {
  const library = useContextLibrary();
  const firstName = user.name?.trim().split(/\s+/)[0];
  return <div className="ws-page">
    <section className="ws-welcome" aria-labelledby="workspace-title"><div><p className="ws-eyebrow">YOUR PERSONAL WORKSPACE</p><h1 id="workspace-title">Welcome back{firstName ? `, ${firstName}` : ""}.</h1><p>Prepare the context MeetGuide can use during your conversations.</p></div><a href="#context-library" className="ws-welcome-link">Add relevant context<ArrowUpRight size={15} aria-hidden="true" /></a></section>
    <PreparationEditor library={library} />
    <DesktopCompanion />
    <p className="ws-page-footnote">Your preparation space. Live assistance happens in MeetGuide Desktop.</p>
  </div>;
}
