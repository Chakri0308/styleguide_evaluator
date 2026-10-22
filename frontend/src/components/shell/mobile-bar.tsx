"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Menu, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { useUIState } from "@/lib/ui-state";
import { SidebarContent } from "./sidebar";

/** Top bar + library drawer for narrow (tablet / phone) screens where the sidebar is hidden. */
export function MobileBar() {
  const ui = useUIState();
  const pathname = usePathname();
  React.useEffect(() => ui.setNavOpen(false), [pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-bg-subtle px-3 md:hidden">
      <DialogPrimitive.Root open={ui.navOpen} onOpenChange={ui.setNavOpen}>
        <DialogPrimitive.Trigger asChild>
          <Button variant="ghost" size="icon" aria-label="Open library">
            <Menu />
          </Button>
        </DialogPrimitive.Trigger>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/30 data-[state=open]:animate-[fade-in_150ms_ease-out]" />
          <DialogPrimitive.Content
            aria-describedby={undefined}
            className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-bg-subtle shadow-lg data-[state=open]:animate-[drawer-in_220ms_var(--ease-spring)]"
          >
            <DialogPrimitive.Title className="sr-only">Library</DialogPrimitive.Title>
            <nav aria-label="Library" className="flex min-h-0 flex-1 flex-col">
              <SidebarContent />
            </nav>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
      <Link href="/" className="font-display text-xl leading-none">
        StyleLens
      </Link>
      <Button variant="ghost" size="icon" className="ml-auto" aria-label="Search" onClick={() => ui.setPaletteOpen(true)}>
        <Search />
      </Button>
    </div>
  );
}
