"use client";

import { ArrowRight, BookMarked, FileCheck2, GitCompareArrows, MessageSquareText } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Kbd } from "@/components/ui/kbd";
import { DropZone } from "@/components/upload/upload-dialog";
import { useGuides } from "@/lib/queries";
import { useUIState } from "@/lib/ui-state";
import { relativeTime } from "@/lib/utils";

const STEPS = [
  { icon: BookMarked, title: "Upload a reference guide", body: "PDF, DOCX, PPTX, Markdown, HTML or images." },
  { icon: FileCheck2, title: "Review the extracted profile", body: "Palette, type system, logo and voice rules — each linked to its source." },
  { icon: GitCompareArrows, title: "Check a candidate", body: "A cited compliance report: matches, deviations, gaps and conflicts." },
  { icon: MessageSquareText, title: "Ask anything", body: "Grounded answers with citations that open the exact passage." },
];

const statusTone = { ready: "ok", failed: "bad", processing: "accent", uploaded: "accent" } as const;

export default function HomePage() {
  const ui = useUIState();
  const { data: guides } = useGuides();
  const recent = guides?.slice(0, 6) ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-6 pb-24 pt-16 md:px-10">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <p className="text-[13px] font-medium text-accent">Style guide intelligence</p>
          <h1 className="mt-2 font-display text-5xl leading-[1.05] tracking-tight text-balance md:text-6xl">
            Every brand rule, <em className="text-fg-muted">in focus.</em>
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-fg-muted">
            StyleLens reads your style guide the way a design lead would — colours, type, logo, imagery and voice —
            then checks any document against it and answers questions with sources you can click.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06 }}
          className="mt-10"
        >
          <DropZone
            onFile={(f) => ui.openUpload("reference", f)}
          />
          <p className="mt-2 text-center text-xs text-fg-subtle">
            Press <Kbd>⌘K</Kbd> to search, <Kbd>⌘U</Kbd> to upload, <Kbd>⌘J</Kbd> to ask the guide.
          </p>
        </motion.div>

        {recent.length > 0 && (
          <section className="mt-14" aria-labelledby="recent-heading">
            <h2 id="recent-heading" className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              Recent
            </h2>
            <ul className="mt-3 divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
              {recent.map((g) => (
                <li key={g.id}>
                  <Link
                    href={`/guides/${g.id}`}
                    className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-bg-subtle"
                  >
                    {g.role === "reference" ? (
                      <BookMarked className="size-4 text-fg-subtle" />
                    ) : (
                      <FileCheck2 className="size-4 text-fg-subtle" />
                    )}
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{g.name}</span>
                    <span className="hidden text-xs uppercase text-fg-subtle sm:inline">{g.format}</span>
                    <Badge tone={statusTone[g.status as keyof typeof statusTone] ?? "neutral"}>{g.status}</Badge>
                    <span className="hidden w-24 text-right text-xs text-fg-subtle sm:inline">
                      {relativeTime(g.created_at)}
                    </span>
                    <ArrowRight className="size-4 -translate-x-1 text-fg-subtle opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="mt-14 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <motion.div
              key={title}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 + i * 0.04 }}
              className="bg-surface p-5"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-fg-subtle">0{i + 1}</span>
                <Icon className="size-4 text-accent" />
              </div>
              <h3 className="mt-3 text-sm font-medium">{title}</h3>
              <p className="mt-1 text-[13px] leading-relaxed text-fg-muted">{body}</p>
            </motion.div>
          ))}
        </section>
      </div>
    </div>
  );
}
