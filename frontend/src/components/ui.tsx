import { AudioLines, ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

export function Brand() {
  return (
    <a className="brand" href="#" aria-label="MeetGuide AI home">
      <AudioLines
        className="brand-mark"
        size={25}
        strokeWidth={1.8}
        aria-hidden="true"
      />
      <span>
        MeetGuide <span className="brand-ai">AI</span>
      </span>
    </a>
  );
}

export function ButtonLink({
  href,
  children,
  secondary = false,
}: {
  href: string;
  children: ReactNode;
  secondary?: boolean;
}) {
  return (
    <a
      className={`button ${secondary ? "button-secondary" : "button-primary"}`}
      href={href}
    >
      {children}
      <ArrowRight size={16} aria-hidden="true" />
    </a>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="eyebrow">{children}</p>;
}
