"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import {
  BookMarked,
  FileCheck2,
  GitCompareArrows,
  Home,
  Laptop,
  MessageSquareText,
  Moon,
  Sun,
  Upload,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Kbd } from "@/components/ui/kbd";
import { useComparisons } from "@/lib/comparison-queries";
import { useGuides } from "@/lib/queries";
import { useTheme } from "@/lib/theme";
import { useUIState } from "@/lib/ui-state";

function Item({
  onSelect,
  icon: Icon,
  children,
  shortcut,
  value,
}: {
  onSelect: () => void;
  icon: React.ElementType;
  children: React.ReactNode;
  shortcut?: string;
  value?: string;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex h-9 cursor-pointer items-center gap-2.5 rounded-md px-2.5 text-sm text-fg-muted data-[selected=true]:bg-surface-sunken data-[selected=true]:text-fg"
    >
      <Icon className="size-4 shrink-0 text-fg-subtle" />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {shortcut && <Kbd>{shortcut}</Kbd>}
    </Command.Item>
  );
}

const groupClass =
  "[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-fg-subtle";

export function CommandPalette() {
  const ui = useUIState();
  const router = useRouter();
  const { setPref } = useTheme();
  const { data: guides } = useGuides();
  const { data: comparisons } = useComparisons();

  const run = (fn: () => void) => {
    ui.setPaletteOpen(false);
    fn();
  };

  return (
    <DialogPrimitive.Root open={ui.paletteOpen} onOpenChange={ui.setPaletteOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/25 data-[state=open]:animate-[fade-in_120ms_ease-out]" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[14vh] z-50 w-[min(92vw,600px)] -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-surface-raised shadow-lg data-[state=open]:animate-[dialog-in_180ms_var(--ease-spring)]"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <Command loop>
            <Command.Input
              autoFocus
              placeholder="Search guides, comparisons and actions…"
              className="h-12 w-full border-b border-border bg-transparent px-4 text-[15px] outline-none placeholder:text-fg-subtle"
            />
            <Command.List className="max-h-[min(60vh,420px)] overflow-y-auto p-1.5">
              <Command.Empty className="px-3 py-8 text-center text-sm text-fg-subtle">No results.</Command.Empty>

              {!!guides?.length && (
                <Command.Group heading="Guides" className={groupClass}>
                  {guides.map((g) => (
                    <Item
                      key={g.id}
                      value={`${g.name} ${g.filename} ${g.role}`}
                      icon={g.role === "reference" ? BookMarked : FileCheck2}
                      onSelect={() => run(() => router.push(`/guides/${g.id}`))}
                    >
                      {g.name}
                      <span className="ml-2 text-xs text-fg-subtle">{g.role}</span>
                    </Item>
                  ))}
                </Command.Group>
              )}

              {!!comparisons?.length && (
                <Command.Group heading="Comparisons" className={groupClass}>
                  {comparisons.map((c) => (
                    <Item
                      key={c.id}
                      value={`compare ${c.candidate_name} ${c.reference_name}`}
                      icon={GitCompareArrows}
                      onSelect={() => run(() => router.push(`/comparisons/${c.id}`))}
                    >
                      {c.candidate_name} <span className="text-fg-subtle">vs</span> {c.reference_name}
                    </Item>
                  ))}
                </Command.Group>
              )}

              <Command.Group heading="Actions" className={groupClass}>
                <Item icon={Upload} shortcut="⌘U" onSelect={() => run(() => ui.openUpload("reference"))}>
                  Upload reference guide
                </Item>
                <Item icon={Upload} onSelect={() => run(() => ui.openUpload("candidate"))}>
                  Upload document to check
                </Item>
                <Item icon={GitCompareArrows} onSelect={() => run(() => router.push("/compare"))}>
                  New comparison
                </Item>
                <Item
                  icon={MessageSquareText}
                  shortcut="⌘J"
                  onSelect={() => run(() => (ui.setChatOpen(true), ui.focusChat()))}
                >
                  Ask the guide
                </Item>
                <Item icon={Home} onSelect={() => run(() => router.push("/"))}>
                  Go home
                </Item>
              </Command.Group>

              <Command.Group heading="Theme" className={groupClass}>
                <Item icon={Sun} onSelect={() => run(() => setPref("light"))}>Light theme</Item>
                <Item icon={Moon} onSelect={() => run(() => setPref("dark"))}>Dark theme</Item>
                <Item icon={Laptop} onSelect={() => run(() => setPref("system"))}>System theme</Item>
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
