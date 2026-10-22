import { cn } from "@/lib/utils";

export function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-surface-sunken px-1 font-mono text-[11px] text-fg-subtle",
        className,
      )}
      {...props}
    />
  );
}
