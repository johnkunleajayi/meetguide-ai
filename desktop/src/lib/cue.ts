import { invoke } from "@tauri-apps/api/core";
export interface CueSnapshot {
  sessionId: number; eventId: number; status: "idle" | "preparing" | "ready" | "error";
  answer: string | null; grounding: "document_supported" | "general_approach" | null;
  sourceCount: number; error: string | null;
}
export const prepareCue = (sessionId: number, eventId: number, retry = false) => invoke<void>("cue_prepare", { sessionId, eventId, retry });
export const clearCue = (sessionId: number, eventId: number) => invoke<void>("cue_clear", { sessionId, eventId });
export const readCue = () => invoke<CueSnapshot>("cue_status");
