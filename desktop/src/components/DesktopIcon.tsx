type Name = "audio" | "mic" | "speaker" | "both" | "shield" | "arrow" | "chevron" | "refresh" | "document" | "code" | "play" | "stop" | "check" | "close";
const paths: Record<Name, string> = {
  audio: "M4 10v4m4-7v10m4-14v18m4-14v10m4-7v4",
  mic: "M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0V5ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8",
  speaker: "M11 4 6 8H3v8h3l5 4V4Zm4 4a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14",
  both: "M4 7h7M4 12h4M4 17h7m3-10h6m-3-3 3 3-3 3m-3 7h6m-3-3 3 3-3 3",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6",
  arrow: "M5 12h14m-6-6 6 6-6 6", chevron: "m6 9 6 6 6-6",
  refresh: "M20 7V3m0 4h-4M4 17v4m0-4h4M5 9a7 7 0 0 1 12-5l3 3M4 17l3 3a7 7 0 0 0 12-5",
  document: "M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h6",
  code: "m8 6-6 6 6 6m8-12 6 6-6 6m-2-15-4 18", play: "m8 4 12 8-12 8V4Z", stop: "M6 6h12v12H6V6Z", check: "m5 12 4 4L19 6", close: "m6 6 12 12M6 18 18 6",
};
export function DesktopIcon({ name, size = 18, className = "" }: { name: Name; size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
