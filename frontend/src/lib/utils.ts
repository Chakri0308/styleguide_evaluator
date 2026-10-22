import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`;
}

export function relativeTime(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (diff < 60) return "just now";
  if (diff < 3600) return fmt.format(-Math.round(diff / 60), "minute");
  if (diff < 86400) return fmt.format(-Math.round(diff / 3600), "hour");
  return fmt.format(-Math.round(diff / 86400), "day");
}
