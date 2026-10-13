import { useEffect, useState } from "react";
type Theme = "light" | "dark";
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const sync = () => {
      try {
        if (!localStorage.getItem("livecue-theme"))
          setTheme(media.matches ? "dark" : "light");
      } catch {
        setTheme(media.matches ? "dark" : "light");
      }
    };
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return {
    theme,
    toggleTheme: () => {
      const next = theme === "dark" ? "light" : "dark";
      setTheme(next);
      try {
        localStorage.setItem("livecue-theme", next);
      } catch {
        /* Theme remains usable without storage. */
      }
    },
  };
}
