import { cn } from "@/lib/utils";

export function ProfileSection({
  id,
  title,
  count,
  description,
  children,
  className,
  actions,
}: {
  id: string;
  title: string;
  count?: number;
  description?: string;
  children: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cn("scroll-mt-28", className)}>
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h2 id={`${id}-title`} className="font-display text-[28px] leading-none tracking-tight">
            {title}
            {count !== undefined && <span className="ml-2 align-middle font-sans text-sm text-fg-subtle">{count}</span>}
          </h2>
          {description && <p className="mt-1.5 text-[13px] text-fg-muted">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-[13px] text-fg-subtle">
      {children}
    </p>
  );
}
