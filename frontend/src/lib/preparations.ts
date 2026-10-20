export const PURPOSES = [
  { id: "job_interview", label: "Job Interview", guidance: "Résumé / CV · Job Description · Company Information · Interview Notes" },
  { id: "sales_meeting", label: "Sales Meeting", guidance: "Client / Company Profile · Product / Service Information · Proposal · Discovery Notes · Previous Meeting Notes" },
  { id: "client_meeting", label: "Client Meeting", guidance: "Client Profile · Project Information · Account Notes · Agenda · Previous Meeting Notes" },
  { id: "internal_meeting", label: "Internal Meeting", guidance: "Agenda · Project Documents · Team Notes · Relevant Reports" },
  { id: "presentation", label: "Presentation / Q&A", guidance: "Presentation / Deck · Supporting Documents · Talking Points · Reference Material" },
  { id: "custom", label: "Custom", guidance: "Any relevant professional context. Documents are optional." },
];
export const CATEGORIES = ["resume", "job_description", "company_profile", "client_profile", "product_information", "proposal", "agenda", "project_document", "meeting_notes", "presentation", "reference_material", "other"];
export const categoryLabel = (id: string) => id === "resume" ? "Résumé / CV" : id.replaceAll("_", " ").replace(/^./, c => c.toUpperCase());
export interface Selection { document_id: string; context_role: string }
export interface PreparationInput { purpose: string; objective: string; documents: Selection[] }
export interface Preparation extends PreparationInput { id: string; active: boolean; created_at: string; updated_at: string }
const API = "http://127.0.0.1:8000/api/preparations";
async function request(path: string, options: RequestInit = {}) {
  const response = await fetch(API + path, { ...options, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json", ...options.headers } });
  if (!response.ok) throw new Error(response.status === 401 ? "Your session expired. Please sign in again." : "Unable to save or load preparation. Check the backend and retry.");
  return response;
}
export const listPreparations = async (signal?: AbortSignal): Promise<Preparation[]> => (await request("", { signal })).json();
export const savePreparation = async (input: PreparationInput, id?: string): Promise<Preparation> => (await request(id ? `/${encodeURIComponent(id)}` : "", { method: id ? "PUT" : "POST", body: JSON.stringify(input) })).json();
export const activatePreparation = async (id: string): Promise<void> => { await request(`/${encodeURIComponent(id)}/activate`, { method: "POST" }); };
