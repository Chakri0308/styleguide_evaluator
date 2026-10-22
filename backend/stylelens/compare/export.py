"""Comparison report export: JSON (machine-readable) and PDF (shareable)."""

import pymupdf

STATUS_COLOR = {"conflict": (0.78, 0.16, 0.16), "deviation": (0.8, 0.45, 0.05), "missing": (0.45, 0.35, 0.7),
                "new": (0.3, 0.45, 0.75), "compliant": (0.15, 0.55, 0.3)}
CATEGORY_LABEL = {"colors": "Color", "typography": "Typography", "logo_rules": "Logo", "imagery_rules": "Imagery",
                  "voice_tone": "Voice & tone", "writing_rules": "Writing", "accessibility": "Accessibility",
                  "components": "Components", "spacing_grid": "Spacing & grid", "misc_rules": "Other"}


def report_json(comp: dict) -> dict:
    return {
        "comparison_id": comp["id"],
        "reference": comp["reference"],
        "candidate": comp["candidate"],
        "created_at": comp["created_at"],
        "score": comp["score"],
        "summary": comp["summary"],
        "findings": [
            {k: f[k] for k in ("finding_id", "category", "status", "severity", "summary", "reasoning",
                               "reference_citations", "candidate_citations", "confidence", "method")}
            for f in comp["findings"]
        ],
    }


class _Writer:
    W, H, M = 612, 792, 50

    def __init__(self):
        self.doc = pymupdf.open()
        self.page = None
        self.y = 0
        self.new_page()

    def new_page(self):
        self.page = self.doc.new_page(width=self.W, height=self.H)
        self.y = self.M

    def ensure(self, h):
        if self.y + h > self.H - self.M:
            self.new_page()

    def text(self, s: str, size=10, bold=False, color=(0.1, 0.1, 0.12), indent=0, gap=1.4):
        font = "hebo" if bold else "helv"
        width = self.W - 2 * self.M - indent
        words, line = s.split(), ""
        lines = []
        for w in words:
            t = f"{line} {w}".strip()
            if pymupdf.get_text_length(t, fontname=font, fontsize=size) <= width:
                line = t
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)
        for ln in lines or [""]:
            self.ensure(size * gap)
            self.page.insert_text((self.M + indent, self.y + size), ln, fontsize=size, fontname=font, color=color)
            self.y += size * gap

    def space(self, h=6):
        self.y += h


def _ascii(s: str) -> str:
    return (s.replace("ΔE", "dE").replace("—", "-").replace("–", "-").replace("“", '"').replace("”", '"')
            .replace("’", "'").replace("‘", "'").replace("…", "...").replace("→", "->"))


def report_pdf(comp: dict) -> bytes:
    w = _Writer()
    w.text("StyleLens compliance report", 22, bold=True)
    w.space(4)
    w.text(_ascii(f"{comp['candidate']['name']}  vs  {comp['reference']['name']}"), 12, color=(0.35, 0.35, 0.4))
    w.text(f"Generated {comp['created_at'][:16].replace('T', ' ')} UTC", 9, color=(0.5, 0.5, 0.55))
    w.space(14)
    w.text(f"Overall compliance: {comp['score']:.0f} / 100", 16, bold=True)
    s = comp["summary"]
    counts = ", ".join(f"{v} {k}" for k, v in sorted(s.get("by_status", {}).items()))
    w.text(f"{s.get('total', 0)} findings: {counts}", 10, color=(0.35, 0.35, 0.4))
    w.space(10)
    w.text("By category", 12, bold=True)
    for cat, d in s.get("categories", {}).items():
        w.text(f"{CATEGORY_LABEL.get(cat, cat)}: {d['score']:.0f}  ({d['total']} findings)", 10, indent=8)
    w.space(12)
    w.text("Findings", 12, bold=True)
    w.space(4)
    for f in comp["findings"]:
        w.ensure(60)
        color = STATUS_COLOR.get(f["status"], (0.3, 0.3, 0.3))
        w.text(_ascii(f"[{f['status'].upper()} · {f['severity']}] {CATEGORY_LABEL.get(f['category'], f['category'])}"),
               8.5, bold=True, color=color)
        w.text(_ascii(f["summary"]), 10)
        if f.get("reasoning"):
            w.text(_ascii(f["reasoning"]), 9, color=(0.35, 0.35, 0.4))
        for label, cites in (("Reference", f["reference_citations"]), ("Candidate", f["candidate_citations"])):
            for c in cites[:2]:
                w.text(_ascii(f"{label} p.{c['page']}: \"{(c.get('quote') or '')[:180]}\""), 8.5, color=(0.45, 0.45, 0.5), indent=10)
        w.space(8)
    return w.doc.tobytes(deflate=True)
