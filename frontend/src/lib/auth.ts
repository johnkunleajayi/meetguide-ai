export const GOOGLE_LOGIN_URL = "http://127.0.0.1:8000/api/auth/google/login";
const API_URL = "http://127.0.0.1:8000/api/auth";

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
}

export async function getCurrentUser(signal: AbortSignal): Promise<AuthUser | null> {
  const response = await fetch(`${API_URL}/me`, {
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Unable to check sign-in. Please try again.");
  const user: AuthUser = await response.json();
  if (!user || typeof user.id !== "string" || typeof user.email !== "string" ||
      !(user.name === null || typeof user.name === "string") ||
      !(user.avatar_url === null || typeof user.avatar_url === "string")) {
    throw new Error("Unable to check sign-in. Please try again.");
  }
  return user;
}

export async function signOut(): Promise<void> {
  // The browser supplies the actual frontend Origin on this cross-origin POST.
  const response = await fetch(`${API_URL}/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) throw new Error("Unable to sign out. Please try again.");
}

// A fixed route intent only, never a token or arbitrary redirect URL.
const WORKSPACE_INTENT = "meetguide-open-workspace";
export function rememberWorkspace() {
  try { sessionStorage.setItem(WORKSPACE_INTENT, "true"); } catch { /* Workspace stays accessible via navigation. */ }
}
export function consumeWorkspaceIntent(): boolean {
  try {
    const pending = sessionStorage.getItem(WORKSPACE_INTENT) === "true";
    sessionStorage.removeItem(WORKSPACE_INTENT);
    return pending;
  } catch { return false; }
}
