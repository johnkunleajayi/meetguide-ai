import { invoke } from "@tauri-apps/api/core";
export type TranscriptSource = "system" | "microphone";
export interface TranscriptEntry { id: number; source: TranscriptSource; text: string; finalText: boolean; interrupted: boolean; offsetMs: number }
export interface TranscriptionStream { source: TranscriptSource; state: string; message: string | null; droppedChunks: number }
export interface TranscriptSnapshot { version: number; sessionId: number; entries: TranscriptEntry[]; streams: TranscriptionStream[]; trimmed: number }
export const readTranscript = (after: number) => invoke<TranscriptSnapshot | null>("transcription_status", { after });
export const sourceLabel = (source: TranscriptSource) => source === "system" ? "Them" : "You";
