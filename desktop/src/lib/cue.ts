import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
export interface CodeAssist { language: string; approach: string; code: string; complexity: string | null; what_to_say: string }
export interface CueCard {
  cueKind?: "conversation" | "code"; codeAssist?: CodeAssist | null;
  attempt?: number; questionId?: string; readyAtUnixMs?: number | null; firstOutputAtUnixMs?: number | null;
  id: number; question: string; status: "queued" | "generating" | "responding" | "ready" | "failed";
  answer: string | null; grounding: "document_supported" | "general_approach" | null;
  sourceCount: number; error: string | null;
}
export interface CueSnapshot { sessionId: number; cards: CueCard[]; notice: string | null }
export const prepareCue = (sessionId: number, eventId: number, retry = false) => invoke<void>("cue_prepare", { sessionId, eventId, retry });
export const clearCue = (sessionId: number, eventId: number) => invoke<void>("cue_clear", { sessionId, eventId });
export const readCue = () => invoke<CueSnapshot>("cue_status");

export const subscribeCue = (update: (snapshot: CueSnapshot) => void) => listen<CueSnapshot>("meetguide-cue-update", event => update(event.payload));
