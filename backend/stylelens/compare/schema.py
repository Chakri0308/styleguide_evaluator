"""Finding schema (the strict JSON shape from the spec) plus the citation shape stored with it."""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["compliant", "deviation", "missing", "conflict", "new"]
Severity = Literal["critical", "major", "minor", "info"]
CATEGORIES = ("colors", "typography", "logo_rules", "imagery_rules", "voice_tone", "writing_rules",
              "accessibility", "components", "spacing_grid", "misc_rules")
Category = Literal["colors", "typography", "logo_rules", "imagery_rules", "voice_tone", "writing_rules",
                   "accessibility", "components", "spacing_grid", "misc_rules"]

RULE_TO_FINDING_CATEGORY = {"color_usage": "colors", "typography_usage": "typography"}


class CitationRef(BaseModel):
    chunk_id: str
    page: int
    quote: str = ""
    element_id: str | None = None
    bbox: list[float] | None = None
    version_id: str | None = None


class FindingModel(BaseModel):
    finding_id: str
    category: Category
    status: Status
    severity: Severity
    summary: str
    reasoning: str = ""
    reference_citations: list[CitationRef] = Field(default_factory=list)
    candidate_citations: list[CitationRef] = Field(default_factory=list)
    confidence: float = 0.0
    method: Literal["deterministic", "llm", "visual", "heuristic"] = "deterministic"
    data: dict = Field(default_factory=dict)


def finding_category(rule_category: str) -> str:
    c = RULE_TO_FINDING_CATEGORY.get(rule_category, rule_category)
    return c if c in CATEGORIES else "misc_rules"
