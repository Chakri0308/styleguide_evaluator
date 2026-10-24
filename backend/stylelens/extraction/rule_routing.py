"""Route every extracted rule to the checker that can verify it: text rules go to the text judge,
visually checkable rules (from text *or* figures) also go to the page-by-page visual check.

"Never reproduce the logo in yellow" is written as text but can only be verified by looking at the
candidate's logo, so it is marked visual_checkable with a concrete check instruction.
"""

import re
from typing import Literal

from pydantic import BaseModel

from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import generate_json, llm_available
from stylelens.schema.profile import RuleItem

BATCH = 40
VISUAL_CATEGORIES = {"logo_rules", "imagery_rules", "spacing_grid", "color_usage", "typography_usage", "components"}
VISUAL_WORDS_RE = re.compile(
    r"\b(logo|lock-?up|wordmark|symbol|colou?rs?|red|yellow|blue|green|orange|black|white|grey|gray|pink|"
    r"purple|gradient|background|photo\w*|image\w*|illustrat\w*|icon\w*|font|typeface|bold|italic|"
    r"weight|size|px|pt|mm|margin|spacing|clear\s*space|align\w*|grid|layout|placement|contrast)\b", re.I)


class RuleRoute(BaseModel):
    id: str
    mode: Literal["visual", "text", "both"]
    subject: Literal["logo", "imagery", "typography", "color", "layout", "text"]
    check: str | None


class RuleRoutes(BaseModel):
    rules: list[RuleRoute]


def heuristic_subject(r: RuleItem) -> str:
    s = r.statement.lower()
    if r.category == "logo_rules" or re.search(r"logo|lock-?up|wordmark|symbol", s):
        return "logo"
    if r.category == "imagery_rules" or re.search(r"photo|image|illustrat|icon", s):
        return "imagery"
    if r.category == "typography_usage" or re.search(r"font|typeface|headline|heading", s):
        return "typography"
    if r.category == "color_usage":
        return "color"
    return "layout"


def heuristic_route(r: RuleItem) -> None:
    if r.category in VISUAL_CATEGORIES or (r.category == "accessibility" and VISUAL_WORDS_RE.search(r.statement)):
        r.visual_checkable = True
        r.visual_subject = r.visual_subject or heuristic_subject(r)


async def route_rules(rules: list[RuleItem], title: str | None, warnings: list[str]) -> None:
    """Sets visual_checkable / visual_subject / check on each rule in place."""
    if not llm_available("extraction"):
        for r in rules:
            heuristic_route(r)
        return
    for i in range(0, len(rules), BATCH):
        batch = rules[i:i + BATCH]
        listing = "\n".join(f"- {r.id} [{r.category} · {r.polarity}] {r.statement}" for r in batch)
        try:
            out = await generate_json("extraction", "classify_rules", RuleRoutes, max_tokens=8000,
                                      guide_title=title or "Untitled guide", rules=listing)
        except (LLMUnavailable, LLMRefusal, ValueError) as exc:
            warnings.append(f"Rule routing fell back to heuristics: {exc}")
            for r in batch:
                heuristic_route(r)
            continue
        routes = {x.id: x for x in out.rules}
        for r in batch:
            x = routes.get(r.id)
            if x is None:
                heuristic_route(r)
            elif x.mode in ("visual", "both"):
                r.visual_checkable = True
                r.visual_subject = x.subject if x.subject != "text" else heuristic_subject(r)
                r.check = r.check or x.check
