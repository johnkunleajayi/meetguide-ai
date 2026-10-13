import {
  AudioLines,
  ChevronDown,
  CircleHelp,
  FileText,
  Layers,
  PanelLeft,
  ShieldCheck,
} from "lucide-react";

const keyPoints = [
  "Review existing Matching Rules",
  "Evaluate Duplicate Rules",
  "Identify affected records and dependencies",
  "Test cleanup in sandbox",
  "Validate before deployment",
];

export function LiveCuePreview() {
  return (
    <section
      className="workspace"
      id="preview"
      aria-label="LiveCue workspace, static concept preview"
    >
      <div className="workspace-toolbar">
        <span className="workspace-brand">
          <AudioLines size={17} aria-hidden="true" /> LiveCue{" "}
          <span>Workspace</span>
        </span>
        <span className="preview-badge">Concept preview</span>
        <PanelLeft size={16} className="muted-icon" aria-hidden="true" />
      </div>
      <div className="session-heading">
        <div>
          <span className="panel-label">LIVE SESSION</span>
          <h2>Salesforce Administrator Interview</h2>
        </div>
        <span className="listening-status">
          <span className="status-dot" />
          Listening
        </span>
      </div>
      <div className="workspace-tabs" aria-hidden="true">
        <span className="active-workspace-tab">Live assistance</span>
        <span>Session context</span>
        <span className="session-duration">12:48</span>
      </div>
      <div className="workspace-content">
        <div className="transcript-heading">
          <span className="panel-label">TRANSCRIPT</span>
          <span>Just now</span>
        </div>
        <div className="transcript-entry">
          <span className="speaker-monogram" aria-hidden="true">
            IN
          </span>
          <div>
            <p className="speaker">Interviewer</p>
            <p className="transcript-question">
              “How would you approach identifying and resolving duplicate
              Account records without disrupting production?”
            </p>
          </div>
        </div>
        <article className="live-cue">
          <div className="cue-heading">
            <span className="panel-label">
              <AudioLines size={15} aria-hidden="true" /> LIVE CUE
            </span>
            <span className="cue-context-label">Contextual response</span>
          </div>
          <blockquote>
            “I'd begin with an audit of the existing Account data and duplicate
            patterns before changing anything in production.”
          </blockquote>
          <p className="key-points-label">KEY POINTS</p>
          <ul className="key-points">
            {keyPoints.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <div className="cue-provenance">
            <span>
              <FileText size={12} aria-hidden="true" />
              Resume
            </span>
            <span>
              <Layers size={12} aria-hidden="true" />
              Role context
            </span>
            <ChevronDown size={13} aria-hidden="true" />
          </div>
        </article>
      </div>
      <div className="workspace-footer">
        <span>
          <ShieldCheck size={12} aria-hidden="true" />
          Permitted conversations only
        </span>
        <span>
          <CircleHelp size={12} aria-hidden="true" />
          Illustrative session
        </span>
      </div>
    </section>
  );
}
