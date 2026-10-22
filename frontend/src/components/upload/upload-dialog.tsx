"use client";

import { useQueryClient } from "@tanstack/react-query";
import { FileUp, UploadCloud } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { API_BASE } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { Guide } from "@/lib/types";
import { useUIState } from "@/lib/ui-state";
import { cn, formatBytes } from "@/lib/utils";

export const ACCEPT = ".pdf,.docx,.pptx,.md,.markdown,.txt,.html,.htm,.png,.jpg,.jpeg,.webp,.svg";
const FORMATS = ["PDF", "DOCX", "PPTX", "Markdown", "TXT", "HTML", "PNG", "JPG", "SVG"];

/** Upload via XHR so we can report byte-level progress. */
function uploadWithProgress(
  file: File,
  role: "reference" | "candidate",
  name: string,
  onProgress: (p: number) => void,
): Promise<Guide> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/guides`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Guide);
      else reject(new Error((body as { detail?: string })?.detail ?? `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error while uploading"));
    const form = new FormData();
    form.append("file", file);
    form.append("role", role);
    if (name.trim()) form.append("name", name.trim());
    xhr.send(form);
  });
}

export function DropZone({
  onFile,
  compact,
  className,
}: {
  onFile: (f: File) => void;
  compact?: boolean;
  className?: string;
}) {
  const [over, setOver] = React.useState(false);
  const input = React.useRef<HTMLInputElement>(null);
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Choose a file to upload or drop it here"
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setOver(false);
        const f = e.dataTransfer.files[0];
        if (f) onFile(f);
      }}
      className={cn(
        "group relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-strong bg-surface-sunken/60 text-center transition-all duration-200",
        "hover:border-accent/60 hover:bg-accent-soft/40",
        over && "scale-[1.01] border-accent bg-accent-soft/60",
        compact ? "px-4 py-8" : "px-6 py-14",
        className,
      )}
    >
      <motion.div
        animate={over ? { y: -4, scale: 1.06 } : { y: 0, scale: 1 }}
        className="grid size-11 place-items-center rounded-xl bg-surface shadow-md ring-1 ring-border"
      >
        <UploadCloud className="size-5 text-accent" />
      </motion.div>
      <div>
        <p className="text-sm font-medium text-fg">
          {over ? "Drop to upload" : "Drop a file here, or click to browse"}
        </p>
        <p className="mt-1 text-xs text-fg-subtle">{FORMATS.join(" · ")} — up to 100 MB</p>
      </div>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function UploadDialog() {
  const ui = useUIState();
  const router = useRouter();
  const qc = useQueryClient();
  const [role, setRole] = React.useState<"reference" | "candidate">("reference");
  const [file, setFile] = React.useState<File | null>(null);
  const [name, setName] = React.useState("");
  const [progress, setProgress] = React.useState<number | null>(null);
  const open = ui.uploadRole !== null;

  React.useEffect(() => {
    if (ui.uploadRole) setRole(ui.uploadRole);
    if (ui.uploadFile) {
      setFile(ui.uploadFile);
      setName(ui.uploadFile.name.replace(/\.[^.]+$/, ""));
    }
  }, [ui.uploadRole, ui.uploadFile]);

  // Dropping a file anywhere on the window opens the dialog with it.
  React.useEffect(() => {
    const onDragOver = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) e.preventDefault();
    };
    const onDrop = (e: DragEvent) => {
      const f = e.dataTransfer?.files[0];
      if (!f) return;
      e.preventDefault();
      ui.openUpload(ui.uploadRole ?? "reference", f);
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [ui]);

  const reset = () => {
    setFile(null);
    setName("");
    setProgress(null);
  };

  const submit = async () => {
    if (!file) return;
    setProgress(0);
    try {
      const guide = await uploadWithProgress(file, role, name, setProgress);
      qc.setQueryData<Guide[]>(keys.guides, (old) => [guide, ...(old ?? [])]);
      qc.setQueryData(keys.guide(guide.id), guide);
      toast.success(`Uploaded ${guide.name}`, { description: "Ingestion started — you can keep working." });
      ui.closeUpload();
      reset();
      router.push(`/guides/${guide.id}`);
    } catch (err) {
      setProgress(null);
      toast.error("Upload failed", { description: err instanceof Error ? err.message : String(err) });
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o && progress === null) {
          ui.closeUpload();
          reset();
        }
      }}
    >
      <DialogContent>
        <DialogTitle className="font-display text-2xl tracking-tight">Upload a document</DialogTitle>
        <DialogDescription className="mt-1 text-sm text-fg-muted">
          A reference guide is your source of truth. A candidate is anything you want to check against it.
        </DialogDescription>

        <div role="radiogroup" aria-label="Document role" className="mt-4 grid grid-cols-2 gap-2">
          {(
            [
              ["reference", "Reference guide", "The source of truth"],
              ["candidate", "Candidate", "A document to check"],
            ] as const
          ).map(([value, label, hint]) => (
            <button
              key={value}
              role="radio"
              aria-checked={role === value}
              onClick={() => setRole(value)}
              className={cn(
                "rounded-lg border px-3 py-2.5 text-left transition-all",
                role === value
                  ? "border-accent bg-accent-soft/50 ring-1 ring-accent"
                  : "border-border hover:border-border-strong",
              )}
            >
              <span className="block text-sm font-medium">{label}</span>
              <span className="block text-xs text-fg-subtle">{hint}</span>
            </button>
          ))}
        </div>

        <div className="mt-4">
          <AnimatePresence mode="wait" initial={false}>
            {file ? (
              <motion.div
                key="file"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                className="rounded-xl border border-border bg-surface-sunken/60 p-3"
              >
                <div className="flex items-center gap-3">
                  <div className="grid size-9 place-items-center rounded-lg bg-surface ring-1 ring-border">
                    <FileUp className="size-4 text-accent" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-fg-subtle">{formatBytes(file.size)}</p>
                  </div>
                  {progress === null && (
                    <Button variant="ghost" size="sm" onClick={reset}>
                      Change
                    </Button>
                  )}
                </div>
                <label className="mt-3 block">
                  <span className="text-xs font-medium text-fg-muted">Display name</span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="mt-1 h-8 w-full rounded-md border border-border bg-surface px-2.5 text-sm outline-none transition-shadow focus:border-accent focus:ring-2 focus:ring-ring"
                  />
                </label>
                {progress !== null && (
                  <div className="mt-3 h-1 overflow-hidden rounded-full bg-border" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
                    <motion.div className="h-full bg-accent" animate={{ width: `${Math.max(progress * 100, 4)}%` }} />
                  </div>
                )}
              </motion.div>
            ) : (
              <motion.div key="drop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <DropZone
                  compact
                  onFile={(f) => {
                    setFile(f);
                    setName(f.name.replace(/\.[^.]+$/, ""));
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => (ui.closeUpload(), reset())} disabled={progress !== null}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={!file || progress !== null}>
            {progress !== null ? `Uploading ${Math.round(progress * 100)}%` : "Upload & analyze"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
