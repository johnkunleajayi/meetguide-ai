import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { GOOGLE_LOGIN_URL, rememberWorkspace, type AuthUser } from "../lib/auth";

function UserAvatar({ user }: { user: AuthUser }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const label = user.name?.trim() || user.email;
  if (user.avatar_url?.startsWith("https://") && failedUrl !== user.avatar_url) {
    return <img className="auth-avatar" src={user.avatar_url} alt="" referrerPolicy="no-referrer"
      onError={() => setFailedUrl(user.avatar_url)} />;
  }
  return <span className="auth-avatar auth-initial" aria-hidden="true">{label[0].toUpperCase()}</span>;
}

export function AuthControls() {
  return <AuthControlsWithState auth={useAuth()} />;
}

export function AuthControlsWithState({ auth, publicSite = false }: { auth: ReturnType<typeof useAuth>; publicSite?: boolean }) {
  const { state, retry, logout, isSigningOut, logoutError } = auth;
  if (state.status === "loading") {
    return <span className="auth-status" role="status">Checking sign-in…</span>;
  }
  if (state.status === "error") {
    return <div className="auth-controls auth-error">
      <span className="auth-status" role="alert">Sign-in check unavailable.</span>
      <button className="sign-in auth-action" onClick={retry}>Retry</button>
    </div>;
  }
  if (state.status === "authenticated") {
    if (publicSite) return <Link className="button button-primary nav-cta" to="/app">Open Workspace</Link>;
    const label = state.user.name?.trim() || state.user.email;
    return <div className="auth-account">
      <div className="auth-controls">
        <UserAvatar user={state.user} />
        <span className="auth-name" title={label}>{label}</span>
        <button className="sign-in auth-action" onClick={logout} disabled={isSigningOut}>
          {isSigningOut ? "Signing out…" : "Sign out"}
        </button>
      </div>
      {logoutError && <span className="auth-status auth-feedback" role="alert">Unable to sign out. Please try again.</span>}
    </div>;
  }
  return <div className="auth-controls">
    <a className="sign-in auth-action" href={GOOGLE_LOGIN_URL} onClick={rememberWorkspace}>Sign in</a>
    <a className="button button-primary nav-cta" href={GOOGLE_LOGIN_URL} onClick={rememberWorkspace}>Get started</a>
  </div>;
}
