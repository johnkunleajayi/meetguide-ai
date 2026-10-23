import { ArrowUpRight, BriefcaseBusiness, MessagesSquare, Presentation } from "lucide-react";
import { Photo } from "./Photo";
import { Reveal } from "./motion";
const scenes = [
  { image: "02_job_interview.png", title: "Job interviews", copy: "Bring your experience into the conversation.", alt: "Professional explaining his experience during a video interview" },
  { image: "04_sales_meeting.png", title: "Sales conversations", copy: "Keep the client's needs and your offer connected.", alt: "Professional discussing a business opportunity on a video call" },
  { image: "05_client_meeting.png", title: "Client meetings", copy: "Respond with the project context in reach.", alt: "Consultant meeting with clients over a video conference" },
  { image: "06_internal_meeting.png", title: "Internal meetings", copy: "Turn shared context into a clearer discussion.", alt: "Colleague discussing team priorities from her workspace" },
];
export function UseCases() {
  return <section id="use-cases" className="mg-use-cases" aria-labelledby="use-cases-title"><div className="mg-container"><Reveal className="mg-use-heading"><div><p className="mg-eyebrow">DIFFERENT ROOMS. THE SAME CONFIDENCE.</p><h2 id="use-cases-title">Made for the moments<br />that move work forward.</h2></div><p>An interview. A client call. A question you didn't see coming. Prepare for the conversation you're actually having.</p></Reveal><div className="mg-use-grid">{scenes.map((scene, i) => <Reveal className={`mg-use-scene mg-use-scene-${i}`} key={scene.image}><article><Photo name={scene.image} alt={scene.alt} /><div><span>0{i + 1}</span><h3>{scene.title}</h3><p>{scene.copy}</p></div></article></Reveal>)}</div><div className="mg-more-contexts"><span><BriefcaseBusiness size={19} />Technical interviews <a href="#code-assist">Explore Code Assist <ArrowUpRight size={13} /></a></span><span><Presentation size={19} />Presentations & Q&A</span><span><MessagesSquare size={19} />Your next important conversation</span></div></div></section>;
}
