import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { useAuth } from "../hooks/useAuth";
import { GOOGLE_LOGIN_URL, rememberWorkspace } from "../lib/auth";

export function RequireAuth({ auth, children }: { auth: ReturnType<typeof useAuth>; children: ReactNode }) {
  if (auth.state.status === "authenticated") return children;
  return <section className="route-message container" aria-labelledby="access-title">
    <h1 id="access-title">Your MeetGuide workspace</h1>
    {auth.state.status === "loading" ? <p role="status">Checking your sign-in…</p> :
      auth.state.status === "error" ? <>
        <p role="alert">We couldn't check your sign-in. Please try again.</p>
        <button className="button button-primary" onClick={auth.retry}>Retry sign-in check</button>
      </> : <>
        <p>Sign in to prepare a conversation, choose relevant context, and continue in MeetGuide Desktop.</p>
        <a className="button button-primary" href={GOOGLE_LOGIN_URL} onClick={rememberWorkspace}>Sign in with Google</a>
      </>}
    <Link className="route-back" to="/">Back to public website</Link>
  </section>;
}
