export type ConversationSpeaker = "them" | "you";
export interface ConversationTurn { id: number; speaker: ConversationSpeaker; text: string; startedAtMs: number; lastSegmentAtMs: number }
export interface MeaningfulEvent {
  id: number; type: "question" | "follow_up_opportunity" | "clarification_opportunity" | "ask_opportunity" | "important_point";
  speaker: ConversationSpeaker; text: string; confidence: number; turnId: number; detectedAtMs: number; context: ConversationTurn[];
}
export interface UnderstandingSnapshot { active: boolean; turns: ConversationTurn[]; events: MeaningfulEvent[]; trimmedTurns: number }
