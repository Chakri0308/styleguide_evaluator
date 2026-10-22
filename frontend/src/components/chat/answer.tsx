"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import type { Citation } from "@/lib/chat";
import { CitationChip } from "./citation";

/** Turn [1], [1][2] and [1, 2] into markdown links the renderer maps to citation chips. */
export function linkCitations(text: string) {
  return text.replace(/\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\](?!\()/g, (_, nums: string) =>
    nums
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );
}

export function Answer({ content, citations, sources }: { content: string; citations: Citation[]; sources: Citation[] }) {
  const byN = React.useMemo(() => {
    const map = new Map<number, Citation>();
    for (const s of sources) map.set(s.n, s);
    for (const c of citations) map.set(c.n, c);
    return map;
  }, [citations, sources]);
  return (
    <div className="answer text-[14px] leading-relaxed text-fg [&_li]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_p+p]:mt-2.5 [&_p+ul]:mt-1.5 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite-")) {
              const n = Number(href.slice(6));
              return <CitationChip n={n} citation={byN.get(n)} />;
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2">
                {children}
              </a>
            );
          },
          code: ({ children }) => <code className="rounded bg-surface-sunken px-1 py-px font-mono text-[12.5px]">{children}</code>,
        }}
      >
        {linkCitations(content)}
      </ReactMarkdown>
    </div>
  );
}
