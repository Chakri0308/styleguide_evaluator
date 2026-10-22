"""Markdown and plain-text parsers. Elements carry source line ranges instead of bboxes."""

import re

from stylelens.ingestion.parsers.base import (
    CODE,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    TABLE,
    ParsedDocument,
    ParsedElement,
    ParsedPage,
    ProgressFn,
)

LIST_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class MarkdownParser:
    name = "markdown"

    def parse(self, data: bytes, filename: str, progress: ProgressFn) -> ParsedDocument:
        lines = _decode(data).splitlines()
        elements: list[ParsedElement] = []
        buf: list[str] = []
        buf_start = 0
        buf_type = PARAGRAPH

        def flush(end: int):
            nonlocal buf, buf_type
            if buf:
                text = "\n".join(buf) if buf_type in (TABLE, CODE) else re.sub(r"\s+", " ", " ".join(buf)).strip()
                if text:
                    elements.append(ParsedElement(buf_type, text, 1, None,
                                                  meta={"line_start": buf_start + 1, "line_end": end}))
            buf, buf_type = [], PARAGRAPH

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("```"):
                flush(i)
                start = i
                i += 1
                code = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code.append(lines[i])
                    i += 1
                elements.append(ParsedElement(CODE, "\n".join(code), 1, None,
                                              meta={"line_start": start + 1, "line_end": i + 1}))
                i += 1
                continue
            m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if m:
                flush(i)
                elements.append(ParsedElement(HEADING, m.group(2), 1, None, level=len(m.group(1)),
                                              meta={"line_start": i + 1, "line_end": i + 1}))
            elif i + 1 < len(lines) and stripped and re.match(r"^(=+|-+)\s*$", lines[i + 1]) and not buf:
                elements.append(ParsedElement(HEADING, stripped, 1, None, level=1 if lines[i + 1].startswith("=") else 2,
                                              meta={"line_start": i + 1, "line_end": i + 2}))
                i += 1
            elif stripped.startswith("|"):
                if buf_type != TABLE:
                    flush(i)
                    buf_type, buf_start = TABLE, i
                buf.append(stripped)
            elif LIST_RE.match(line):
                flush(i)
                buf_type, buf_start = LIST_ITEM, i
                buf.append(LIST_RE.sub("", line, count=1))
            elif not stripped:
                flush(i)
            else:
                if buf_type == TABLE:
                    flush(i)
                if not buf:
                    buf_start = i
                buf.append(stripped.lstrip("> "))
            i += 1
            if i % 200 == 0:
                progress(i / len(lines), f"Line {i} of {len(lines)}")
        flush(len(lines))
        progress(1.0, "Done")
        title = next((e.text for e in elements if e.type == HEADING), None)
        return ParsedDocument(parser=self.name, title=title, pages=[ParsedPage(1, 612.0, 792.0)],
                              elements=elements, meta={"paged": False, "line_count": len(lines)})


class TextParser(MarkdownParser):
    """Plain text: blank-line separated paragraphs; short ALL-CAPS or underlined lines become headings."""

    name = "text"

    def parse(self, data: bytes, filename: str, progress: ProgressFn) -> ParsedDocument:
        text = _decode(data)
        converted = []
        for line in text.splitlines():
            s = line.strip()
            if s and len(s) <= 60 and s.isupper() and any(c.isalpha() for c in s):
                converted.append(f"## {s.title()}")
            else:
                converted.append(line.replace("#", "\\#") if line.lstrip().startswith("#") else line)
        doc = super().parse("\n".join(converted).encode(), filename, progress)
        doc.parser = self.name
        return doc
