import {
  ArrowRight,
  AudioLines,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  FileText,
  NotebookPen,
} from "lucide-react";
import { Eyebrow } from "./ui";

const sources = [
  { title: "Resume", detail: "Your experience and expertise", icon: FileText },
  {
    title: "Job description",
    detail: "The role and its priorities",
    icon: BriefcaseBusiness,
  },
  {
    title: "Meeting notes",
    detail: "What has already been discussed",
    icon: NotebookPen,
  },
  {
    title: "Company context",
    detail: "The business behind the conversation",
    icon: Building2,
  },
  {
    title: "Personal knowledge",
    detail: "The information you bring",
    icon: BookOpen,
  },
];

export function ContextSection() {
  return (
    <section className="context-section" aria-labelledby="context-title">
      <div className="container">
        <div className="section-heading">
          <div>
            <Eyebrow>CONTEXTUAL INTELLIGENCE</Eyebrow>
            <h2 id="context-title">
              The right answer starts
              <br />
              with the right context.
            </h2>
          </div>
          <p>
            A conversation is only part of the picture.
            <br />
            Relevant knowledge makes the cue yours.
          </p>
        </div>
        <div
          className="context-diagram"
          aria-label="Resume, job description, meeting notes, company context, and personal knowledge inform one concise Live Cue"
        >
          <div className="context-sources">
            {sources.map(({ title, detail, icon: Icon }) => (
              <div className="context-source" key={title}>
                <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
                <div>
                  <h3>{title}</h3>
                  <p>{detail}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="context-bridge" aria-hidden="true">
            <span className="context-engine">
              <AudioLines size={26} strokeWidth={1.5} />
            </span>
            <ArrowRight size={17} className="context-arrow" />
          </div>
          <article className="context-output">
            <span className="panel-label">
              <AudioLines size={15} aria-hidden="true" /> ONE CONCISE LIVE CUE
            </span>
            <blockquote>
              “In my previous role, I used a sandbox-first approach to validate
              data changes. I'd bring that same discipline to your production
              environment.”
            </blockquote>
            <div className="context-output-footer">
              <span>Experience + role + conversation</span>
              <span className="example-label">Illustrative response</span>
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
