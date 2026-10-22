export function HighlightBox({ bbox, scale, strong }: { bbox: number[]; scale: number; strong?: boolean }) {
  const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = bbox;
  const pad = 3;
  return (
    <div
      aria-hidden
      data-highlight
      className={
        "pointer-events-none absolute rounded-[3px] transition-opacity duration-300 " +
        (strong
          ? "bg-warn/10 ring-2 ring-warn shadow-[0_0_0_4px_color-mix(in_oklch,var(--warn)_20%,transparent)]"
          : "bg-highlight mix-blend-multiply dark:mix-blend-normal")
      }
      style={{
        left: x0 * scale - pad,
        top: y0 * scale - pad,
        width: (x1 - x0) * scale + pad * 2,
        height: (y1 - y0) * scale + pad * 2,
      }}
    />
  );
}
