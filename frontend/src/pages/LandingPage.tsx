import { ArrowRight, ArrowUpRight, BriefcaseBusiness, Check, FileText, Handshake, LockKeyhole, Monitor, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { HeroConversation } from "../components/HeroConversation";
import { ProductDemo } from "../components/ProductDemo";

const useCases = [
  { icon: BriefcaseBusiness, title: "Interviews", copy: "Answer with specific experience from your career." },
  { icon: Handshake, title: "Sales conversations", copy: "Respond to product and customer questions in the moment." },
  { icon: Users, title: "Professional meetings", copy: "Explain your work and decisions clearly." },
  { icon: Monitor, title: "Client conversations", copy: "Discuss project experience with clients and stakeholders." },
];

export function LandingPage() {
  return <>
    <section className="marketing-hero marketing-container" id="product" aria-labelledby="hero-title">
      <div className="hero-kicker"><span /> Your real-time AI meeting assistant.</div>
      <div className="marketing-hero-grid">
        <div className="marketing-hero-copy">
          <h1 id="hero-title">Stay present.<br />Know what <span>to say.</span></h1>
          <p>MeetGuide listens to the conversation, understands the question, and draws on your experience to prepare a natural answer you can actually speak.</p>
          <div className="marketing-actions"><Link className="marketing-button" to="/app">Prepare your context <ArrowUpRight size={17} aria-hidden="true" /></Link><a className="marketing-text-link" href="#demo">See it in action <ArrowRight size={16} aria-hidden="true" /></a></div>
          
        </div>
        <HeroConversation />
      </div>
      <ProductDemo />
    </section>
    <section className="marketing-context marketing-container" id="your-context" aria-labelledby="context-heading">
      <div className="context-story"><p className="marketing-eyebrow">YOUR EXPERIENCE IS THE DIFFERENCE</p><h2 id="context-heading">Start with what<br /><span>makes you, you.</span></h2><p>Upload your résumé or CV to your private Context Library. MeetGuide retrieves relevant excerpts to personalize Live Cues without inventing experience.</p><Link className="marketing-text-link" to="/app">Prepare your Context Library <ArrowRight size={16} aria-hidden="true" /></Link></div>
      <div className="context-illustration" aria-label="Illustration of a fictional résumé informing an answer"><div className="context-document"><div className="context-document-top"><FileText size={22} aria-hidden="true" /><span>My résumé<span>PRIVATE CONTEXT LIBRARY</span></span><LockKeyhole size={14} aria-hidden="true" /></div><div className="document-line" /><div className="document-line short" /><p className="context-highlight">Salesforce integrations<br />External APIs & field mapping<br />Sandbox testing</p><div className="document-line" /><div className="document-line short" /><span className="context-sample">Illustrative content</span></div><div className="context-relevance"><Check size={16} aria-hidden="true" /><span>The relevant experience.<br /><strong>Right when you need it.</strong></span></div><p className="context-formats">RÉSUMÉ / CV <span>PDF</span><span>DOCX</span><span>TXT</span></p></div>
    </section>
    <section className="marketing-setup marketing-container" aria-labelledby="setup-title"><div><h2 id="setup-title">A workspace to prepare.<br /><span>A companion for the conversation.</span></h2></div><div className="setup-steps"><div><span>01 / ON THE WEB</span><h3>Make it yours.</h3><p>Manage your context in the web workspace.</p></div><ArrowRight className="setup-arrow" size={22} aria-hidden="true" /><div><span>02 / ON WINDOWS</span><h3>Take it live.</h3><p>Sign in to MeetGuide Desktop, select your audio source, and start your session.</p></div></div></section>
    <section className="marketing-use-cases marketing-container" id="use-cases" aria-labelledby="use-case-heading"><div className="marketing-section-heading"><h2 id="use-case-heading">For your next<br /><span>important conversation.</span></h2></div><div className="professional-cases">{useCases.map(({ icon: Icon, title, copy }) => <article key={title}><Icon size={23} strokeWidth={1.4} aria-hidden="true" /><div><h3>{title}</h3><p>{copy}</p></div></article>)}</div></section>
    <section className="marketing-privacy marketing-container" id="privacy" aria-labelledby="privacy-title"><div className="privacy-heading"><LockKeyhole size={23} strokeWidth={1.5} aria-hidden="true" /><p className="marketing-eyebrow">PERSONAL CONTEXT. CLEAR BOUNDARIES.</p><h2 id="privacy-title">Built around<br /><span>your conversation.</span></h2></div><div className="privacy-details"><div><h3>Session-only live content</h3><p>Live audio and transcripts stay session-only in the current desktop architecture; MeetGuide does not save them to disk or its database.</p></div><div><h3>Your private Context Library</h3><p>Only your account can access your documents. Deleting one removes its stored file and extracted context.</p></div><div><h3>Clear about provider processing</h3><p>Transcription providers process audio. AI providers receive relevant questions, conversation and context to prepare answers.</p></div></div></section>
    <section className="marketing-closing marketing-container" aria-labelledby="closing-title"><span className="closing-mark" aria-hidden="true">↗</span><h2 id="closing-title">Your experience.<br /><span>The words to share it.</span></h2><Link className="marketing-button" to="/app">Open your workspace <ArrowUpRight size={17} aria-hidden="true" /></Link></section>
  </>;
}
