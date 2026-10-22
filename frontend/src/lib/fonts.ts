"use client";

import * as React from "react";

// Families we can load from Google Fonts for live specimens. Others fall back to the stack.
const GOOGLE_FONTS = new Set([
  "Inter", "Roboto", "Open Sans", "Lato", "Montserrat", "Poppins", "Source Sans 3", "Source Serif 4", "Noto Sans",
  "Noto Serif", "Raleway", "Nunito", "Nunito Sans", "Work Sans", "Rubik", "IBM Plex Sans", "IBM Plex Serif",
  "IBM Plex Mono", "DM Sans", "DM Serif Display", "Manrope", "Karla", "Fraunces", "Playfair Display", "Merriweather",
  "Lora", "PT Sans", "PT Serif", "Libre Baskerville", "Crimson Pro", "EB Garamond", "Cormorant", "Space Grotesk",
  "Space Mono", "JetBrains Mono", "Fira Sans", "Fira Code", "Ubuntu", "Oswald", "Barlow", "Mulish", "Quicksand",
  "Archivo", "Instrument Sans", "Instrument Serif", "Geist", "Geist Mono",
]);

const requested = new Map<string, Promise<void>>();

function loadStylesheet(href: string): Promise<void> {
  return new Promise((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.onload = () => resolve();
    link.onerror = () => resolve();
    document.head.appendChild(link);
  });
}

export type FontState = "loading" | "loaded" | "fallback";

/** Loads a Google Font for specimens; reports whether the real face is available. */
export function useSpecimenFont(family: string): FontState {
  const [state, setState] = React.useState<FontState>(GOOGLE_FONTS.has(family) ? "loading" : "fallback");
  React.useEffect(() => {
    if (!GOOGLE_FONTS.has(family)) {
      // Might be installed locally (e.g. Helvetica, Georgia)
      setState(document.fonts.check(`16px "${family}"`) ? "loaded" : "fallback");
      return;
    }
    if (!requested.has(family)) {
      requested.set(
        family,
        loadStylesheet(
          `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}:wght@300;400;500;600;700;800&display=swap`,
        ),
      );
    }
    let cancelled = false;
    requested
      .get(family)!
      .then(() => document.fonts.load(`400 24px "${family}"`))
      .then((faces) => !cancelled && setState(faces.length ? "loaded" : "fallback"))
      .catch(() => !cancelled && setState("fallback"));
    return () => {
      cancelled = true;
    };
  }, [family]);
  return state;
}

export function weightNumber(weight?: string | null): number | undefined {
  if (!weight) return undefined;
  const m = weight.match(/(\d00)/);
  return m ? Number(m[1]) : undefined;
}
