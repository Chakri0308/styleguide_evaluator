"""Atomic rule extraction.

Primary path: the LLM reads each section (elements tagged with ids) and returns atomic rules under a
strict JSON schema with the ids it drew from. Fallback path (no LLM configured): directive-sentence
heuristics. Both produce RuleItems with source refs that point at real elements.
"""

import logging
import re

from pydantic import BaseModel

from stylelens.extraction.common import (
    DIRECTIVE_RE,
    QUANTITY_RE,
    El,
    categorize,
    clauses,
    normative_level,
    polarity,
)
from stylelens.llm.client import generate_json
from stylelens.schema.profile import RuleCategory, RuleItem

log = logging.getLogger(__name__)

SECTION_CHAR_BUDGET = 9000


# -- heuristic ------------------------------------------------------------------------------------
STRONG_RE = re.compile(r"\b(must|never|always|should|do not|don't|avoid|required|may not|only|at least|no more than)\b", re.I)
IMPERATIVE_RE = re.compile(
    r"^(use|keep|write|place|pair|set|apply|ensure|make|limit|spell|capitali[sz]e|prefer|show|address|say|"
    r"choose|select|include|add|align|left-align|reserve|leave|maintain|give|follow)\b", re.I)
CAPTION_RE = re.compile(r"^(fig(?:ure)?\.?\s*\d+|table\s+\d+)", re.I)
NON_RULE_SECTION_RE = re.compile(r"\b(mission|about|introduction|history|overview|contents|story)\b", re.I)


def _is_rule(text: str, section: str) -> bool:
    if len(text) < 12 or len(text) > 600 or CAPTION_RE.match(text):
        return False
    if STRONG_RE.search(text) or IMPERATIVE_RE.match(text):
        return not NON_RULE_SECTION_RE.search(section.split(" > ")[-1] if section else "")
    return False


def heuristic_rules(elements: list[El]) -> list[RuleItem]:
    rules: list[RuleItem] = []
    seen: set[str] = set()
    for el in elements:
        if el.type in ("heading", "image", "swatch") or CAPTION_RE.match(el.text):
            continue
        section = el.section
        units: list[str]
        if el.type == "table":
            rows = el.meta.get("rows") or []
            header = [h.lower() for h in rows[0]] if rows else []
            if len(header) == 2 and {"use", "avoid"} <= set(header):
                units = [f"Use \"{r[0]}\" instead of \"{r[1]}\"." for r in rows[1:] if len(r) >= 2 and r[0] and r[1]]
            else:
                continue
        elif el.type == "list_item":
            units = [el.text]
        else:
            units = clauses(el.text)
        for unit in units:
            unit = unit.strip()
            key = unit.lower()
            if key in seen or CAPTION_RE.match(unit):
                continue
            if el.type == "list_item":
                if len(unit) < 8 or NON_RULE_SECTION_RE.search(el.heading_path[-1] if el.heading_path else ""):
                    continue
            elif not _is_rule(unit, section):
                continue
            seen.add(key)
            q = QUANTITY_RE.search(unit)
            rules.append(RuleItem(
                id=f"rule-{len(rules) + 1}",
                category=categorize(section, unit),
                statement=unit,
                value=q.group(0) if q else None,
                polarity=polarity(unit, el.meta.get("marker"), section),
                normative_level=normative_level(unit),
                source_refs=[el.ref(unit)],
            ))
    return rules


# -- LLM ------------------------------------------------------------------------------------------
class ExtractedRule(BaseModel):
    statement: str
    category: RuleCategory
    normative_level: str  # must | should | may
    polarity: str  # do | dont
    value: str | None
    subject: str | None
    element_ids: list[str]
    quote: str


class ExtractedRules(BaseModel):
    rules: list[ExtractedRule]


def sections(elements: list[El]) -> list[list[El]]:
    """Group consecutive elements by their top two heading levels, splitting oversize groups."""
    groups: list[list[El]] = []
    current: list[El] = []
    key = None
    size = 0
    for el in elements:
        if el.type == "swatch":
            continue
        k = tuple(el.heading_path[:2])
        text_len = len(el.text) + 40
        if current and (k != key or size + text_len > SECTION_CHAR_BUDGET):
            groups.append(current)
            current, size = [], 0
        current.append(el)
        key = k
        size += text_len
    if current:
        groups.append(current)
    return groups


def _render_section(group: list[El]) -> str:
    lines = []
    for el in group:
        label = {"list_item": "item", "heading": f"h{el.level or ''}"}.get(el.type, el.type)
        text = el.text if el.type != "image" else (el.meta.get("caption") or "[image]")
        lines.append(f"[{el.id}] ({label}) {text}")
    return "\n".join(lines)


async def llm_rules(elements: list[El], title: str | None) -> list[RuleItem]:
    by_id = {e.id: e for e in elements}
    rules: list[RuleItem] = []
    for group in sections(elements):
        if not any(e.type in ("paragraph", "list_item", "table") for e in group):
            continue
        out = await generate_json(
            "extraction", "extract_rules", ExtractedRules,
            guide_title=title or "Untitled guide",
            section_path=" > ".join(group[0].heading_path) or "(document start)",
            elements=_render_section(group),
        )
        for r in out.rules:
            refs = [by_id[i].ref(r.quote or by_id[i].text) for i in r.element_ids if i in by_id]
            if not refs:  # never keep an uncited rule
                log.info("dropping rule without valid element ids: %s", r.statement[:80])
                continue
            rules.append(RuleItem(
                id=f"rule-{len(rules) + 1}",
                category=r.category,
                statement=r.statement.strip(),
                value=r.value,
                role=r.subject,
                polarity="dont" if r.polarity == "dont" else "do",
                normative_level=r.normative_level if r.normative_level in ("must", "should", "may") else "should",
                source_refs=refs,
            ))
    return rules
