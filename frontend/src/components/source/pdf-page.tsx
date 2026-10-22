"use client";

import * as React from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { HighlightBox } from "./highlight-box";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

export interface Highlight {
  bbox: number[];
  strong?: boolean;
}

/** One PDF page rendered with PDF.js plus bbox highlight overlays (bbox in PDF points). */
export default function PdfPage({
  url,
  page,
  width,
  highlights,
  onLoad,
}: {
  url: string;
  page: number;
  width: number;
  highlights: Highlight[];
  onLoad?: (numPages: number) => void;
}) {
  const [pageSize, setPageSize] = React.useState<{ w: number; h: number } | null>(null);
  const scale = pageSize ? width / pageSize.w : 1;
  const file = React.useMemo(() => ({ url }), [url]);

  return (
    <Document
      file={file}
      onLoadSuccess={(d) => onLoad?.(d.numPages)}
      loading={<div className="skeleton" style={{ width, height: width * 1.29 }} />}
      error={<p className="p-4 text-sm text-bad">Couldn&apos;t load the PDF.</p>}
    >
      <div className="relative" style={{ width }}>
        <Page
          pageNumber={page}
          width={width}
          renderAnnotationLayer={false}
          onLoadSuccess={(p) => setPageSize({ w: p.originalWidth, h: p.originalHeight })}
          loading={<div className="skeleton" style={{ width, height: width * 1.29 }} />}
        />
        {pageSize &&
          highlights.map((h, i) => (
            <HighlightBox key={i} bbox={h.bbox} scale={scale} strong={h.strong} />
          ))}
      </div>
    </Document>
  );
}
