import { useEffect, useRef, useState } from "react";
import { getCurrentUser, signOut, type AuthUser } from "../lib/auth";

type AuthState =
  | { status: "loading" | "unauthenticated" | "error"; user?: never }
  | { status: "authenticated"; user: AuthUser };

export function useAuth() {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const logoutPending = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    getCurrentUser(controller.signal).then((user) => {
      if (!controller.signal.aborted) {
        setState(user ? { status: "authenticated", user } : { status: "unauthenticated" });
      }
    }).catch(() => {
      if (!controller.signal.aborted) setState({ status: "error" });
    });
    return () => controller.abort();
  }, [attempt]);

  function retry() {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }

  async function logout() {
    if (logoutPending.current) return;
    logoutPending.current = true;
    setIsSigningOut(true);
    setLogoutError(false);
    try {
      await signOut();
      setState({ status: "unauthenticated" });
    } catch {
      setLogoutError(true);
    } finally {
      logoutPending.current = false;
      setIsSigningOut(false);
    }
  }

  return { state, retry, logout, isSigningOut, logoutError };
}
