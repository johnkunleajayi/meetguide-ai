import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../src/App";
const user = { id: "u1", email: "fictional@example.test", name: "Jordan Rivera", avatar_url: null };
const doc = { id: "d1", name: "fictional-project.txt", context_type: "project_document", media_type: "text/plain", status: "ready", size_bytes: 50, created_at: "2026-10-20T00:00:00Z" };
const prep = { id: "p1", purpose: "client_meeting", objective: "Review fictional Alpha project", documents: [{document_id:"d1",context_role:"project_document"}], active: true, created_at: "2026-10-20T00:00:00Z", updated_at: "2026-10-20T00:00:00Z" };
const reply = (status: number, body: unknown = null) => ({ok:status < 300, status, json: async () => body});
function show(documents = [doc], preparations: typeof prep[] = []) {
 const fetch = vi.fn((url: string, options?: RequestInit) => Promise.resolve(
 url.endsWith("/me") ? reply(200,user) : url.endsWith("/logout") ? reply(204) : url.endsWith("/activate") ? reply(204) :
 options?.method === "DELETE" ? reply(204) : options?.method === "POST" && url.endsWith("/documents") ? reply(201,doc) :
 ["POST","PUT"].includes(options?.method || "") ? reply(201,{...prep,...JSON.parse(options!.body as string)}) :
 url.endsWith("/preparations") ? reply(200,preparations) : reply(200,documents)));
 vi.stubGlobal("fetch", fetch); render(<MemoryRouter initialEntries={["/app"]}><AppRoutes /></MemoryRouter>); return fetch;
}
async function choose() {
 await screen.findByRole("heading",{name:"What are you preparing for?"});
 await waitFor(() => expect((screen.getByRole("radio",{name:"Sales Meeting"}) as HTMLInputElement).disabled).toBe(false));
 fireEvent.click(screen.getByRole("radio",{name:"Sales Meeting"}));
 fireEvent.change(screen.getByLabelText("2. What would you like to accomplish?"),{target:{value:"Discovery with fictional Beta"}});
}
beforeEach(() => { localStorage.clear(); sessionStorage.clear(); vi.stubGlobal("matchMedia",vi.fn(() => ({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn()}))); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it("personalizes preparation and never automatically selects an existing document", async () => {
 show(); await choose(); expect(screen.getByText("Welcome back, Jordan.")).toBeTruthy();
 expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
 expect(screen.getByText("0 context documents selected · General assistance")).toBeTruthy();
 expect(screen.queryByRole("link",{name:"Public website"})).toBeNull();
 expect(screen.getByRole("link",{name:"Relevant context"}).getAttribute("href")).toBe("#context-library");
});
it("saves a no-document preparation and activates it through authenticated APIs",async () => {
 const fetch=show([]); await choose(); fireEvent.click(screen.getByRole("button",{name:"Save & use preparation"}));
 await screen.findByText(/Preparation saved and selected/);
 const call=fetch.mock.calls.find(([url,opt])=>url.endsWith("/preparations") && opt?.method==="POST")!;
 expect(JSON.parse(call[1]!.body as string)).toEqual({purpose:"sales_meeting",objective:"Discovery with fictional Beta",documents:[]});
 expect(call[1]!.credentials).toBe("include"); expect(fetch.mock.calls.some(([url])=>url.endsWith("/p1/activate"))).toBe(true);
});
it("selects reusable context with a role and detaches without deleting it",async () => {
 const fetch=show(); await choose(); fireEvent.click(screen.getByRole("checkbox"));
 expect(screen.getByText("1 context document selected")).toBeTruthy();
 fireEvent.click(screen.getByRole("button",{name:"Save & use preparation"})); await screen.findByText(/Preparation saved and selected/);
 const saved=fetch.mock.calls.find(([url,opt])=>url.endsWith("/preparations") && opt?.method==="POST")!;
 expect(JSON.parse(saved[1]!.body as string).documents).toEqual([{document_id:"d1",context_role:"project_document"}]);
 fireEvent.click(screen.getByRole("button",{name:"Remove from preparation"}));
 expect(screen.getByText("fictional-project.txt")).toBeTruthy(); expect(fetch.mock.calls.some(([,opt])=>opt?.method==="DELETE")).toBe(false);
 fireEvent.click(screen.getByRole("button",{name:"Save & use preparation"})); await waitFor(()=>expect(fetch.mock.calls.some(([,opt])=>opt?.method==="PUT" && JSON.parse(opt.body as string).documents.length===0)).toBe(true));
});
it("loads an active preparation with its real count and purpose",async () => {
 show([doc],[prep]); await waitFor(()=>expect((screen.getByLabelText("2. What would you like to accomplish?") as HTMLTextAreaElement).value).toBe(prep.objective));
 expect(screen.getByText("1 context document selected")).toBeTruthy(); expect((screen.getByRole("radio",{name:"Client Meeting"}) as HTMLInputElement).checked).toBe(true);
 fireEvent.change(screen.getByLabelText("Saved preparations"),{target:{value:""}});
 expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
});
it("uploads context with a category and selects only the uploaded document",async () => {
 const fetch=show([]); await choose(); fireEvent.change(screen.getByLabelText("Context type for new document"),{target:{value:"proposal"}});
 const file=new File(["Fictional proposal"],"proposal.txt",{type:"text/plain"});
 fireEvent.change(screen.getByLabelText("Upload context document"),{target:{files:[file]}}); fireEvent.click(screen.getByRole("button",{name:"Upload document"}));
 await screen.findByText("1 context document selected");
 expect(fetch.mock.calls.find(([url,opt])=>url.endsWith("/documents") && opt?.method==="POST")![1]!.headers).toEqual(expect.objectContaining({"X-Context-Type":"proposal"}));
});
it("distinguishes canceling delete from confirmed account deletion",async () => {
 const fetch=show(); await choose(); const confirm=vi.fn(()=>false); vi.stubGlobal("confirm",confirm);
 fireEvent.click(screen.getByRole("button",{name:"Delete fictional-project.txt from account"})); expect(fetch.mock.calls.some(([,opt])=>opt?.method==="DELETE")).toBe(false);
 confirm.mockReturnValue(true); fireEvent.click(screen.getByRole("button",{name:"Delete fictional-project.txt from account"}));
 await waitFor(()=>expect(screen.queryByText("fictional-project.txt")).toBeNull()); expect(fetch.mock.calls.some(([,opt])=>opt?.method==="DELETE")).toBe(true);
});

it("retains a saved preparation when activation fails and retries without duplicating it",async()=>{
 const fetch=show([]);await choose();const original=fetch.getMockImplementation()!;let attempts=0;
 fetch.mockImplementation((url,opt)=>url.endsWith("/activate") && attempts++===0 ? Promise.resolve(reply(503)) : original(url,opt));
 fireEvent.click(screen.getByRole("button",{name:"Save & use preparation"}));await screen.findByText(/Preparation saved, but it could not/);
 expect(screen.queryByText(/Preparation saved and selected/)).toBeNull();
 fireEvent.click(screen.getByRole("button",{name:"Save & use preparation"}));await screen.findByText(/Preparation saved and selected/);
 expect(fetch.mock.calls.filter(([url,opt])=>url.endsWith("/preparations") && opt?.method==="POST")).toHaveLength(1);
 expect(fetch.mock.calls.some(([,opt])=>opt?.method==="PUT")).toBe(true);
});

it("keeps long objectives and document names intact in preparation and summary", async () => {
 const objective = "Review the client implementation and agree on the next delivery milestones. ".repeat(6).trim();
 const name = "client-implementation-notes-".repeat(8) + ".txt";
 show([{ ...doc, name }], [{ ...prep, objective }]);
 const summary = await screen.findByRole("region", { name: "Client Meeting" }, { timeout: 5000 });
 expect(within(summary).getByText(objective)).toBeTruthy();
 expect(within(summary).getByRole("button", { name: "Save & use preparation" })).toBeTruthy();
 const documentLabel = await screen.findByText(name);
 expect(documentLabel.closest("label")?.querySelector("input[type=checkbox]")).toBeTruthy();
 expect((screen.getByLabelText("2. What would you like to accomplish?") as HTMLTextAreaElement).value).toBe(objective);
});

it("saves optional technical interview preferences without requiring documents", async () => {
 const fetch = show([]); await choose();
 fireEvent.click(screen.getByRole("radio", { name: "Job Interview" }));
 fireEvent.click(screen.getByRole("checkbox", { name: "Technical/Coding interview" }));
 expect((screen.getByLabelText("Preferred coding language") as HTMLSelectElement).value).toBe("auto");
 fireEvent.change(screen.getByLabelText("Preferred coding language"), { target: { value: "python" } });
 fireEvent.click(screen.getByRole("button", { name: "Save & use preparation" }));
 await screen.findByText(/Preparation saved and selected/);
 const saved = fetch.mock.calls.find(([url, opt]) => url.endsWith("/preparations") && opt?.method === "POST")!;
 expect(JSON.parse(saved[1]!.body as string)).toEqual(expect.objectContaining({ purpose: "job_interview", technical_interview: true, coding_language: "python", documents: [] }));
});
