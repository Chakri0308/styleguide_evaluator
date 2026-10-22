"use client";

import {
  BookMarked,
  FileCheck2,
  GitCompareArrows,
  Laptop,
  Loader2,
  Moon,
  Plus,
  Search,
  Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { useComparisons } from "@/lib/comparison-queries";
import { useGuides } from "@/lib/queries";
import { useTheme, type ThemePref } from "@/lib/theme";
import type { Guide } from "@/lib/types";
import { useUIState } from "@/lib/ui-state";
import { cn } from "@/lib/utils";

function StatusDot({ status }: { status: string }) {
  if (status === "processing" || status === "uploaded")
    return <Loader2 aria-label="Processing" className="size-3.5 animate-spin text-accent" />;
  if (status === "failed") return <span aria-label="Failed" className="size-1.5 rounded-full bg-bad" />;
  return null;
}

function NavItem({ href, children, active }: { href: string; children: React.ReactNode; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex h-8 items-center gap-2 rounded-md px-2 text-[13px] text-fg-muted transition-colors duration-150",
        "hover:bg-surface-sunken hover:text-fg",
        active && "bg-surface text-fg shadow-sm ring-1 ring-border",
      )}
    >
      {children}
    </Link>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-5">
      <div className="mb-1 flex h-6 items-center justify-between pl-2 pr-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">{title}</h2>
        {action}
      </div>
      <div className="flex flex-col gap-px">{children}</div>
    </section>
  );
}

function GuideList({ guides, empty }: { guides: Guide[]; empty: string }) {
  const pathname = usePathname();
  if (guides.length === 0) return <p className="px-2 py-1 text-[12px] text-fg-subtle">{empty}</p>;
  return guides.map((g) => (
    <NavItem key={g.id} href={`/guides/${g.id}`} active={pathname.startsWith(`/guides/${g.id}`)}>
      <span className="min-w-0 flex-1 truncate">{g.name}</span>
      <StatusDot status={g.status} />
    </NavItem>
  ));
}

const THEME_OPTIONS: { value: ThemePref; label: string; icon: React.ElementType }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Laptop },
];

function ThemeSwitch() {
  const { pref, setPref } = useTheme();
  return (
    <div role="radiogroup" aria-label="Theme" className="flex rounded-md bg-surface-sunken p-0.5">
      {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
        <Tooltip key={value} content={label}>
          <button
            role="radio"
            aria-checked={pref === value}
            aria-label={label}
            onClick={() => setPref(value)}
            className={cn(
              "flex h-6 flex-1 items-center justify-center rounded-[5px] text-fg-subtle transition-colors",
              pref === value ? "bg-surface text-fg shadow-sm" : "hover:text-fg",
            )}
          >
            <Icon className="size-3.5" />
          </button>
        </Tooltip>
      ))}
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const ui = useUIState();
  const { data: guides, isLoading } = useGuides();
  const { data: comparisons } = useComparisons();
  const refs = guides?.filter((g) => g.role === "reference") ?? [];
  const cands = guides?.filter((g) => g.role === "candidate") ?? [];

  return (
    <nav
      aria-label="Library"
      className="hidden w-60 shrink-0 flex-col border-r border-border bg-bg-subtle md:flex"
    >
      <div className="flex h-12 items-center gap-2 px-4">
        <Link href="/" className="flex items-center gap-2 rounded-md" aria-label="StyleLens home">
          <span className="relative grid size-6 place-items-center rounded-md bg-fg text-bg">
            <span className="size-2.5 rounded-full border-[2.5px] border-current" />
          </span>
          <span className="font-display text-[21px] leading-none tracking-tight">StyleLens</span>
        </Link>
      </div>

      <div className="px-3">
        <button
          onClick={() => ui.setPaletteOpen(true)}
          className="flex h-8 w-full items-center gap-2 rounded-md border border-border bg-surface px-2 text-[13px] text-fg-subtle shadow-sm transition-colors hover:border-border-strong hover:text-fg-muted"
        >
          <Search className="size-3.5" />
          <span className="flex-1 text-left">Search…</span>
          <Kbd>⌘K</Kbd>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        <Section
          title="Reference guides"
          action={
            <Tooltip content="Upload reference guide (⌘U)">
              <button
                aria-label="Upload reference guide"
                onClick={() => ui.openUpload("reference")}
                className="rounded p-1 text-fg-subtle hover:bg-surface-sunken hover:text-fg"
              >
                <Plus className="size-3.5" />
              </button>
            </Tooltip>
          }
        >
          {isLoading ? (
            <div className="flex flex-col gap-1.5 px-2 py-1">
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-4 w-28" />
            </div>
          ) : (
            <GuideList guides={refs} empty="No reference guides yet." />
          )}
        </Section>

        <Section
          title="Candidates"
          action={
            <Tooltip content="Upload document to check">
              <button
                aria-label="Upload candidate document"
                onClick={() => ui.openUpload("candidate")}
                className="rounded p-1 text-fg-subtle hover:bg-surface-sunken hover:text-fg"
              >
                <Plus className="size-3.5" />
              </button>
            </Tooltip>
          }
        >
          {!isLoading && <GuideList guides={cands} empty="Nothing to check yet." />}
        </Section>

        <Section
          title="Comparisons"
          action={
            <Tooltip content="New comparison">
              <Link
                href="/compare"
                aria-label="New comparison"
                className="rounded p-1 text-fg-subtle hover:bg-surface-sunken hover:text-fg"
              >
                <Plus className="size-3.5" />
              </Link>
            </Tooltip>
          }
        >
          {comparisons?.length ? (
            comparisons.map((c) => (
              <NavItem key={c.id} href={`/comparisons/${c.id}`} active={pathname === `/comparisons/${c.id}`}>
                <GitCompareArrows className="size-3.5 shrink-0 text-fg-subtle" />
                <span className="min-w-0 flex-1 truncate">{c.candidate_name}</span>
                {c.status === "ready" && c.score != null ? (
                  <span className="font-mono text-[11px] tabular-nums text-fg-subtle">{Math.round(c.score)}</span>
                ) : (
                  <StatusDot status={c.status === "failed" ? "failed" : "processing"} />
                )}
              </NavItem>
            ))
          ) : (
            <p className="px-2 py-1 text-[12px] text-fg-subtle">No comparisons yet.</p>
          )}
        </Section>
      </div>

      <div className="flex flex-col gap-2 border-t border-border p-3">
        <div className="flex items-center gap-2 text-[12px] text-fg-subtle">
          <BookMarked className="size-3.5" /> {refs.length}
          <FileCheck2 className="ml-2 size-3.5" /> {cands.length}
          <GitCompareArrows className="ml-2 size-3.5" /> {comparisons?.length ?? 0}
        </div>
        <ThemeSwitch />
      </div>
    </nav>
  );
}
