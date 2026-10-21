import { invoke } from "@tauri-apps/api/core";
export interface Preparation { technical_interview?: boolean; coding_language?: string; id: string; purpose: string; objective: string; documents: { document_id: string; context_role: string }[]; active: boolean; updated_at: string }
export const readPreparations = () => invoke<Preparation[]>("preparation_list");
export const activatePreparation = (id: string) => invoke<void>("preparation_activate", { id });
export const purposeLabel = (id: string) => ({ job_interview: "Job Interview", sales_meeting: "Sales Meeting", client_meeting: "Client Meeting", internal_meeting: "Internal Meeting", presentation: "Presentation / Q&A", custom: "Custom" })[id as "custom"] || id.replaceAll("_", " ");

export const codingLanguageLabel = (id: string) => ({ auto: "Auto-detect language", python: "Python", javascript: "JavaScript", typescript: "TypeScript", java: "Java", apex: "Apex", csharp: "C#", go: "Go", sql: "SQL", other: "Other" })[id as "auto"] || id;
