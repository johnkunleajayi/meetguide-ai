import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

export interface PrivateDisplayStatus {
  state: "on" | "off" | "limited" | "unknown" | "unsupported";
  requestedEnabled: boolean;
  message: string | null;
  revision: number;
}

export const privateDisplayAvailable = isTauri;
export const readPrivateDisplay = () => invoke<PrivateDisplayStatus>("private_display_status");
export const setPrivateDisplay = (enabled: boolean) =>
  invoke<PrivateDisplayStatus>("private_display_set", { enabled });
export const subscribePrivateDisplay = (update: (status: PrivateDisplayStatus) => void) =>
  listen<PrivateDisplayStatus>("meetguide-private-display", event => update(event.payload));
