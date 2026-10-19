import {
  ArrowUpRight,
  BriefcaseBusiness,
  Handshake,
  MessagesSquare,
  Moon,
  Sun,
  Users,
} from "lucide-react";
import { Brand, ButtonLink, Eyebrow } from "./components/ui";
import { MeetGuidePreview } from "./components/MeetGuidePreview";
import { ContextSection } from "./components/ContextSection";
import { AuthControls } from "./components/AuthControls";
import { useTheme } from "./hooks/useTheme";
import { workflow } from "./data/workflow";

const useCases = [
  {
    name: "Interviews",
    description: "Connect your experience to the question in front of you.",
    icon: BriefcaseBusiness,
  },
  {
    name: "Meetings",
    description: "Bring relevant context to the decisions that matter.",
    icon: Users,
  },
  {
    name: "Sales calls",
    description: "Respond to the customer's priorities with clarity.",
    icon: Handshake,
  },
  {
    name: "High-stakes conversations",
    description:
      "Keep your attention on the conversation, with support at hand.",
    icon: MessagesSquare,
  },
];

export default function App() {
  const { theme, toggleTheme } = useTheme();
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="header-shell">
        <div className="site-header container">
          <Brand />
          <nav className="main-nav" aria-label="Main navigation">
            <a href="#product">Product</a>
            <a href="#how-it-works">How it works</a>
            <a href="#use-cases">Use cases</a>
          </nav>
          <div className="header-actions">
            <button
              className="theme-button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <AuthControls />
          </div>
        </div>
      </header>
      <main id="main">
        <section className="hero container" id="product">
          <div className="hero-copy">
            <Eyebrow>REAL-TIME CONVERSATION INTELLIGENCE</Eyebrow>
            <h1>
              Know what to say.
              <br />
              <span>When it matters.</span>
            </h1>
            <p className="hero-description">
              MeetGuide AI listens to permitted conversations, understands what is
              being asked, and surfaces relevant talking points in real time.
            </p>
            <div className="hero-actions">
              <ButtonLink href="#preview">Start a session</ButtonLink>
              <ButtonLink href="#how-it-works" secondary>
                See how it works
              </ButtonLink>
            </div>
            <p className="hero-trust">
              Built for interviews, meetings, sales calls and high-stakes
              conversations.
            </p>
          </div>
          <div className="hero-preview">
            <MeetGuidePreview />
            <p className="preview-disclosure">
              Product concept · Sample transcript and cues · No microphone
              connected
            </p>
          </div>
        </section>
        <section
          className="workflow-section container"
          id="how-it-works"
          aria-labelledby="workflow-title"
        >
          <div className="section-heading">
            <div>
              <Eyebrow>HOW IT WORKS</Eyebrow>
              <h2 id="workflow-title">From spoken question to useful cue.</h2>
            </div>
            <p>
              A focused flow of intelligence.
              <br />
              Designed to keep you in the conversation.
            </p>
          </div>
          <ol className="workflow">
            {workflow.map(({ name, description }, index) => (
              <li className="workflow-step" key={name}>
                <div className="step-rail">
                  <span className="step-number">0{index + 1}</span>
                </div>
                <h3>{name}</h3>
                <p>{description}</p>
              </li>
            ))}
          </ol>
        </section>
        <ContextSection />
        <section
          className="use-cases-section container"
          id="use-cases"
          aria-labelledby="use-cases-title"
        >
          <div className="section-heading">
            <div>
              <Eyebrow>BUILT FOR THE MOMENT</Eyebrow>
              <h2 id="use-cases-title">
                Clarity across the conversations that count.
              </h2>
            </div>
          </div>
          <div className="use-cases-grid">
            {useCases.map(({ name, description, icon: Icon }) => (
              <article className="use-case" key={name}>
                <Icon size={22} strokeWidth={1.5} aria-hidden="true" />
                <h3>{name}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="closing container">
          <div>
            <Eyebrow>LIVE CUE. CLEAR THINKING.</Eyebrow>
            <h2>
              Your knowledge.
              <br />
              Available when it matters.
            </h2>
            <p>Your real-time AI meeting assistant.</p>
          </div>
          <a className="button button-primary" href="#preview">
            Explore the workspace
            <ArrowUpRight size={16} aria-hidden="true" />
          </a>
        </section>
      </main>
      <footer className="container">
        <div className="footer-main">
          <Brand />
          <span>© {new Date().getFullYear()} MeetGuide AI</span>
          <a href="#how-it-works">How it works</a>
        </div>
        <p className="footer-disclosure">
          Frontend concept preview. Live sessions and AI
          assistance are not available yet.
        </p>
      </footer>
    </>
  );
}
