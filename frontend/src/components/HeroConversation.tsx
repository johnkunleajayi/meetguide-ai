import { useState } from "react";
import "./HeroConversation.css";

export function HeroConversation() {
  const [failed, setFailed] = useState(false);
  return <figure className="hero-conversation">
    <div className="hero-owned-scene">
      {failed ? <div className="hero-asset-fallback"><strong>Stay in the conversation.</strong><p>MeetGuide turns a question and your relevant experience into an answer you can speak.</p><a href="#demo">Explore the interactive demonstration below</a></div> : <img
        src="/images/meetguide-hero-conversation.png"
        width={1672} height={941} decoding="async" fetchPriority="high"
        alt="A professional in a video conversation, with MeetGuide connecting a Salesforce question to relevant experience and a ready-to-speak answer."
        onError={() => setFailed(true)}
      />}
    </div>
    <figcaption>Illustrative MeetGuide conversation · Explore the interactive demonstration below.</figcaption>
  </figure>;
}
