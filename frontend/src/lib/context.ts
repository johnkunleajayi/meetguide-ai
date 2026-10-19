const API = "http://127.0.0.1:8000/api/context";
export const MAX_DOCUMENT_BYTES = 5 * 1024 * 1024;
export interface ContextDocument {
  id: string; name: string; context_type: string; media_type: string;
  size_bytes: number; status: "ready" | "deleting"; created_at: string;
}

async function request(path: string, options: RequestInit = {}) {
  const response = await fetch(`${API}${path}`, { ...options, credentials: "include", cache: "no-store" });
  if (!response.ok) {
    if (response.status === 401) throw new Error("Your session has expired. Please sign in again.");
    if (response.status === 413) throw new Error("Maximum upload size is 5 MB.");
    if (response.status === 422) {
      const body = await response.json().catch(() => null);
      if (typeof body?.detail === "string") throw new Error(body.detail);
    }
    throw new Error("Context Library is unavailable. Please retry.");
  }
  return response;
}
export async function listDocuments(signal: AbortSignal): Promise<ContextDocument[]> {
  return (await request("/documents", { signal })).json();
}
export async function uploadDocument(file: File, signal: AbortSignal): Promise<ContextDocument> {
  if (!file.size) throw new Error("The document is empty.");
  if (file.size > MAX_DOCUMENT_BYTES) throw new Error("Maximum upload size is 5 MB.");
  if (!/\.(pdf|docx|txt)$/i.test(file.name)) throw new Error("Choose a PDF, DOCX or UTF-8 TXT file.");
  return (await request("/documents", { method: "POST", signal, body: file, headers: { "Content-Type": "application/octet-stream", "X-Document-Name": encodeURIComponent(file.name) } })).json();
}
export async function deleteDocument(id: string, signal: AbortSignal): Promise<void> {
  await request(`/documents/${encodeURIComponent(id)}`, { method: "DELETE", signal });
}
