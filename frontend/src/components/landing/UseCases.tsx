import { ArrowUpRight, Presentation } from "lucide-react";
import { Link } from "react-router-dom";
import { Photo } from "./Photo";
import { Reveal } from "./motion";
const cases = [
  { title: "Job Interviews", image: "02_job_interview.png", alt: "Professional discussing a question during a remote interview", copy: "Bring your experience into the answer, with context you've chosen." },
  { title: "Technical Interviews", image: "03_technical_interview.png", alt: "Developer explaining a solution at a laptop", copy: "Work through an approach, code and the explanation behind it." },
  { title: "Sales Conversations", image: "04_sales_meeting.png", alt: "Sales professional speaking with a prospective customer", copy: "Keep your product context close when the questions come." },
  { title: "Client Meetings", image: "05_client_meeting.png", alt: "Consultant talking with colleagues on a video call", copy: "Respond with the project and account context that matters." },
  { title: "Internal Meetings", image: "06_internal_meeting.png", alt: "Team member discussing plans in a remote internal meeting", copy: "Explain decisions and trade-offs without losing the thread." },
];
export function UseCases() {
  return <section className="mg-use-cases mg-light" id="use-cases" aria-labelledby="use-cases-title"><div className="mg-container"><Reveal className="mg-section-heading"><div><p className="mg-eyebrow">FOR THE CONVERSATIONS THAT COUNT</p><h2 id="use-cases-title">Different moments.<br />A little more prepared.</h2></div><p>Choose your purpose. Bring relevant context.<br />Let the conversation lead.</p></Reveal><div className="mg-case-grid">{cases.map(item => <Reveal key={item.title}><article className="mg-case"><div className="mg-case-photo"><Photo name={item.image} alt={item.alt} /></div><div><h3>{item.title}</h3><p>{item.copy}</p></div></article></Reveal>)}<Reveal><article className="mg-case mg-presentation-case"><div className="mg-presentation-art" aria-hidden="true"><Presentation size={44} strokeWidth={1} /><span>THE NEXT QUESTION</span><strong>You've got<br />the context.</strong><i /></div><div><h3>Presentations / Q&A</h3><p>Keep supporting material in reach when the discussion opens up.</p><Link to="/app">Prepare a session <ArrowUpRight size={14} aria-hidden="true" /></Link></div></article></Reveal></div></div></section>;
}
