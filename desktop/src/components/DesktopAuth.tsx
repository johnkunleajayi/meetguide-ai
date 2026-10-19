import { useEffect, useRef, useState } from "react";
import { cancelLogin, login, logout, nativeAvailable, restoreAuth, type AuthUser } from "../lib/auth";

type Status = "checking" | "signed-out" | "signed-in" | "signing-in" | "signing-out" | "error" | "browser-preview";

export function DesktopAuth() {
  const [status, setStatus] = useState<Status>("checking");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [failedAvatar, setFailedAvatar] = useState<string | null>(null);
  const busy = useRef(false);

  useEffect(() => {
    let active = true;
    if (!nativeAvailable()) { setStatus("browser-preview"); return; }
    restoreAuth().then((profile) => {
      if (active) { setUser(profile); setStatus(profile ? "signed-in" : "signed-out"); }
    }).catch(() => {
      if (active) { setStatus("error"); setError("Unable to restore your session. Check the backend connection and Windows credential access, then retry."); }
    });
    return () => { active = false; };
  }, [attempt]);

  async function startLogin() {
    if (busy.current) return;
    busy.current = true;
    setStatus("signing-in");
    setError(null);
    try {
      setUser(await login());
      setStatus("signed-in");
    } catch (reason) {
      setStatus("signed-out");
      setError(typeof reason === "string" ? reason : "Unable to sign in. Please try again.");
    } finally { busy.current = false; }
  }

  async function signOut() {
    if (busy.current) return;
    busy.current = true;
    setStatus("signing-out");
    setError(null);
    try {
      await logout();
      setUser(null);
      setStatus("signed-out");
    } catch (reason) {
      setStatus("signed-in");
      setError(typeof reason === "string" ? reason : "Unable to sign out. Please try again.");
    } finally { busy.current = false; }
  }

  const label = user?.name?.trim() || user?.email || "";
  return <section className="auth-panel" aria-label="MeetGuide account">
    {status === "checking" && <p className="auth-note" role="status">Checking your account…</p>}
    {status === "browser-preview" && <p className="auth-note">Open the Tauri desktop app to sign in securely.</p>}
    {status === "signed-out" && <button className="auth-button auth-primary" onClick={startLogin}>Sign in with Google</button>}
    {status === "signing-in" && <>
      <p className="auth-note" role="status">Complete sign-in in your browser, then return here.</p>
      <button className="auth-button" onClick={() => { void cancelLogin().catch(() => setError("Unable to cancel. Please wait for sign-in to time out.")); }}>Cancel sign-in</button>
    </>}
    {user && (status === "signed-in" || status === "signing-out") && <div className="auth-profile">
      {user.avatar_url?.startsWith("https://") && failedAvatar !== user.avatar_url ?
        <img className="auth-avatar" src={user.avatar_url} alt="" referrerPolicy="no-referrer" onError={() => setFailedAvatar(user.avatar_url)} /> :
        <span className="auth-avatar auth-initial" aria-hidden="true">{label[0]?.toUpperCase()}</span>}
      <div className="auth-identity"><span className="auth-name" title={label}>{label}</span><span className="auth-email" title={user.email}>{user.email}</span></div>
      <button className="auth-button" disabled={status === "signing-out"} onClick={signOut}>{status === "signing-out" ? "Signing out…" : "Sign out"}</button>
    </div>}
    {error && <p className="auth-note auth-error" role="alert">{error}</p>}
    {status === "error" && <button className="auth-button" onClick={() => { setError(null); setStatus("checking"); setAttempt((value) => value + 1); }}>Retry</button>}
  </section>;
}
