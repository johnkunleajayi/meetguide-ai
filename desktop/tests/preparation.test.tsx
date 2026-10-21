import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { PreparationPicker } from "../src/components/PreparationPicker";
import * as api from "../src/lib/preparation";
vi.mock("../src/lib/preparation", async (original) => ({ ...await original<typeof import("../src/lib/preparation")>(), readPreparations:vi.fn(), activatePreparation:vi.fn() }));
const first={id:"a",purpose:"sales_meeting",objective:"Fictional Alpha",documents:[],active:true,updated_at:"v1"};
const second={...first,id:"b",purpose:"client_meeting",objective:"Fictional Beta",active:false};
function Harness({locked=false,authenticated=true}:{locked?:boolean;authenticated?:boolean}) {const [value,onChange]=useState<api.Preparation|null>(null);return <PreparationPicker {...{locked,authenticated,value,onChange}}/>;}
afterEach(()=>{cleanup();vi.resetAllMocks();});
it("reviews the active preparation and deliberately activates another",async()=>{
 vi.mocked(api.readPreparations).mockResolvedValue([first,second]);vi.mocked(api.activatePreparation).mockResolvedValue();render(<Harness/>);
 await screen.findByText("Fictional Alpha");fireEvent.change(screen.getByLabelText("Change preparation"),{target:{value:"b"}});
 await screen.findByText("Fictional Beta");expect(api.activatePreparation).toHaveBeenCalledWith("b");
});
it("does not offer changes during a live session",async()=>{
 vi.mocked(api.readPreparations).mockResolvedValue([first]);const view=render(<Harness/>);await screen.findByText("Fictional Alpha");view.rerender(<Harness locked/>);
 expect(screen.getByText("Fixed for this session")).toBeTruthy();expect(screen.queryByLabelText("Change preparation")).toBeNull();expect(screen.queryByText("Refresh preparations")).toBeNull();
});
it("handles no preparation and clears selection on logout",async()=>{
 vi.mocked(api.readPreparations).mockResolvedValue([]);const view=render(<Harness/>);await screen.findByText(/Create a preparation/);
 view.rerender(<Harness authenticated={false}/>);await waitFor(()=>expect(screen.queryByRole("region")).toBeNull());expect(api.activatePreparation).not.toHaveBeenCalled();
});
it("keeps failed loading explicit and supports refresh",async()=>{
 vi.mocked(api.readPreparations).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce([first]);render(<Harness/>);
 await screen.findByRole("alert");fireEvent.click(screen.getByText("Refresh preparations"));await screen.findByText("Fictional Alpha");
});

it("loads the reviewed interview preparation and refreshes without losing its revision", async () => {
 const interview = { ...first, purpose: "job_interview", objective: "Salesforce Administrator interview with TrueCar", documents: [{document_id:"fictional-document", context_role:"resume"}], updated_at:"reviewed-revision" };
 vi.mocked(api.readPreparations).mockResolvedValue([interview]); render(<Harness/>);
 await screen.findByText(interview.objective);
 expect(screen.getByText("Job Interview")).toBeTruthy(); expect(screen.getByText("1 context document")).toBeTruthy();
 fireEvent.click(screen.getByText("Refresh preparations"));
 await screen.findByText(interview.objective); expect(api.readPreparations).toHaveBeenCalledTimes(2);
 await expect(vi.mocked(api.readPreparations).mock.results[1].value).resolves.toEqual([interview]);
});

it("shows frozen technical interview language preferences in the compact review", async () => {
 vi.mocked(api.readPreparations).mockResolvedValue([{...first,purpose:"job_interview",technical_interview:true,coding_language:"csharp"}]);
 render(<Harness locked />);
 await screen.findByText(/Technical\/Coding interview/);
 expect(screen.getByText(/Technical\/Coding interview/).textContent).toContain("C#");
 expect(screen.getByText("Fixed for this session")).toBeTruthy();
});
