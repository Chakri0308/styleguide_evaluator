import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium leading-4 tracking-wide",
  {
    variants: {
      tone: {
        neutral: "bg-surface-sunken text-fg-muted",
        accent: "bg-accent-soft text-accent-soft-fg",
        ok: "bg-ok-soft text-ok",
        warn: "bg-warn-soft text-warn",
        bad: "bg-bad-soft text-bad",
        info: "bg-info-soft text-info",
        new: "bg-new-soft text-new",
      },
      outline: { true: "bg-transparent ring-1 ring-inset ring-current/25" },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  outline,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone, outline }), className)} {...props} />;
}
