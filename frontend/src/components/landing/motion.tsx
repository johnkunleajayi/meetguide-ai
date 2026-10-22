import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

const MotionContext = createContext({ paused: false, reduced: false, toggle: () => {} });
export function LandingMotion({ children }: { children: ReactNode }) {
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  return <MotionContext.Provider value={{ paused, reduced, toggle: () => setPaused(value => !value) }}>
    <div className="public-site" data-motion={paused || reduced ? "paused" : "playing"}>{children}</div>
  </MotionContext.Provider>;
}
export const useLandingMotion = () => useContext(MotionContext);

// One small clock per demonstration. Offscreen, background-tab and paused demos do no timer work.
export function useDemoClock(duration: number, completed: number) {
  const { paused, reduced } = useLandingMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [activeTab, setActiveTab] = useState(!document.hidden);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!ref.current || !window.IntersectionObserver) { setVisible(true); return; }
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: .12 });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const change = () => setActiveTab(!document.hidden);
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  useEffect(() => {
    if (paused || reduced || !visible || !activeTab) return;
    const timer = window.setInterval(() => setTick(value => (value + 100) % duration), 100);
    return () => window.clearInterval(timer);
  }, [duration, paused, reduced, visible, activeTab]);
  return { ref, tick: reduced ? completed : tick };
}

export function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [entered, setEntered] = useState(false);
  const { reduced } = useLandingMotion();
  useEffect(() => {
    if (!ref.current || !window.IntersectionObserver || reduced) { setEntered(true); return; }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setEntered(true); observer.disconnect(); }
    }, { threshold: .1 });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [reduced]);
  return <div ref={ref} className={`mg-reveal ${className}`} data-entered={entered || reduced}>{children}</div>;
}
