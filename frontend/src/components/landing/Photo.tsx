type PhotoProps = { name: string; alt: string; className?: string; priority?: boolean };
// Optimized derivatives of the approved local originals; no remote photography.
export function Photo({ name, alt, className, priority = false }: PhotoProps) {
  const stem = name.replace(/\.png$/, "");
  return <picture><source type="image/webp" srcSet={`/images/landing/${stem}-640.webp 640w, /images/landing/${stem}-1280.webp 1280w`} sizes={priority ? "(max-width: 680px) 100vw, 55vw" : "(max-width: 680px) 100vw, (max-width: 950px) 50vw, 33vw"} /><img className={className} src={`/references/${name}`} width="1672" height="941" alt={alt} loading={priority ? "eager" : "lazy"} fetchPriority={priority ? "high" : "auto"} decoding="async" /></picture>;
}
