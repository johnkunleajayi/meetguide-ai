import { invoke, isTauri } from "@tauri-apps/api/core";

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
}

export const nativeAvailable = isTauri;
export const restoreAuth = () => invoke<AuthUser | null>("auth_restore");
export const login = () => invoke<AuthUser>("auth_login");
export const logout = () => invoke<void>("auth_logout");
export const cancelLogin = () => invoke<void>("auth_cancel");
