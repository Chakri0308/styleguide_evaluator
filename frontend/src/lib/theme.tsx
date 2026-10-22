"use client";

import * as React from "react";

export type ThemePref = "light" | "dark" | "system";
const KEY = "stylelens-theme";

/** Inline script run before paint to avoid a flash of the wrong theme. */
export const themeInitScript = `(()=>{try{var p=localStorage.getItem("${KEY}")||"system";var d=p==="dark"||(p==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d)}catch(e){}})()`;

const ThemeContext = React.createContext<{ pref: ThemePref; resolved: "light" | "dark"; setPref: (p: ThemePref) => void }>({
  pref: "system",
  resolved: "light",
  setPref: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [pref, setPrefState] = React.useState<ThemePref>("system");
  const [systemDark, setSystemDark] = React.useState(false);

  React.useEffect(() => {
    try {
      setPrefState((localStorage.getItem(KEY) as ThemePref) || "system");
    } catch {
      /* storage unavailable */
    }
    const mq = matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const resolved = pref === "system" ? (systemDark ? "dark" : "light") : pref;

  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
  }, [resolved]);

  const setPref = React.useCallback((p: ThemePref) => {
    setPrefState(p);
    try {
      localStorage.setItem(KEY, p);
    } catch {
      /* storage unavailable */
    }
  }, []);

  return <ThemeContext.Provider value={{ pref, resolved, setPref }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => React.useContext(ThemeContext);
