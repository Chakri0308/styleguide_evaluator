"""Canonical Style Schema. Every guide — whatever its format — is normalised into this shape so two
guides can be compared field by field. TypeScript types are generated from it via OpenAPI."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NormativeLevel = Literal["must", "should", "may"]
Polarity = Literal["do", "dont"]

RULE_CATEGORIES = (
    "logo_rules", "spacing_grid", "imagery_rules", "voice_tone", "writing_rules",
    "components", "accessibility", "color_usage", "typography_usage", "misc_rules",
)
class Model(BaseModel):
    # Response schemas list defaulted fields as required so generated TS types are non-optional.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


RuleCategory = Literal[
    "logo_rules", "spacing_grid", "imagery_rules", "voice_tone", "writing_rules",
    "components", "accessibility", "color_usage", "typography_usage", "misc_rules",
]


class SourceRef(Model):
    element_id: str
    page: int
    bbox: list[float] | None = None
    quote: str = ""
    chunk_id: str | None = None


class ColorItem(Model):
    id: str
    name: str | None = None
    role: str | None = None  # primary | secondary | accent | background | text | neutral | error | ...
    value: str  # canonical HEX
    hex: str
    rgb: str | None = None
    cmyk: str | None = None
    hsl: str | None = None
    pantone: str | None = None
    lab: list[float]
    normative_level: NormativeLevel = "should"
    status: Literal["approved", "prohibited"] = "approved"
    usage: list[str] = Field(default_factory=list)
    origin: list[Literal["text", "swatch", "image", "llm"]] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class TypographyItem(Model):
    id: str
    role: str  # display | h1..h6 | body | caption | ui | label | code | ...
    family: str
    weight: str | None = None
    size: str | None = None
    line_height: str | None = None
    letter_spacing: str | None = None
    case: str | None = None
    fallbacks: list[str] = Field(default_factory=list)
    value: str  # human summary e.g. "Fraunces Semibold 48px/56px"
    normative_level: NormativeLevel = "should"
    usage: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class RuleItem(Model):
    id: str
    category: RuleCategory
    statement: str  # atomic, self-contained rule
    value: str | None = None  # key quantity, e.g. "24px", "4.5:1"
    role: str | None = None  # subject the rule is about, e.g. "logo", "body text", "headlines"
    polarity: Polarity = "do"
    normative_level: NormativeLevel = "should"
    source_refs: list[SourceRef] = Field(default_factory=list)
    # Visual rules (clear space, placement, proportions, misuse…) learned from the guide's diagrams.
    visual: bool = False
    check: str | None = None  # how to verify the rule by looking at a page
    figure: SourceRef | None = None  # the diagram that illustrates the rule (bbox in page points)


class ImageItem(Model):
    id: str
    element_id: str
    page: int
    bbox: list[float] | None = None
    image_url: str
    kind: str = "other"  # logo | photo | illustration | icon | diagram | swatch_sheet | screenshot | other
    example: Literal["do", "dont", "neutral"] = "neutral"
    description: str = ""
    caption: str | None = None
    rules_depicted: list[str] = Field(default_factory=list)
    dominant_colors: list[str] = Field(default_factory=list)
    text_in_image: str | None = None
    described_by: str = "heuristic"  # heuristic | <model id>


class FontUsage(Model):
    family: str
    sizes: list[float] = Field(default_factory=list)
    bold: bool = False
    chars: int = 0
    embedded: bool = False


class ProfileStats(Model):
    pages: int = 0
    elements: int = 0
    rules: int = 0
    colors: int = 0
    images: int = 0
    visual_rules: int = 0
    llm_used: bool = False
    extraction_model: str | None = None
    warnings: list[str] = Field(default_factory=list)


class StyleProfile(Model):
    schema_version: Literal[1] = 1
    version_id: str
    title: str | None = None
    summary: str | None = None
    colors: list[ColorItem] = Field(default_factory=list)
    typography: list[TypographyItem] = Field(default_factory=list)
    logo_rules: list[RuleItem] = Field(default_factory=list)
    spacing_grid: list[RuleItem] = Field(default_factory=list)
    imagery_rules: list[RuleItem] = Field(default_factory=list)
    voice_tone: list[RuleItem] = Field(default_factory=list)
    writing_rules: list[RuleItem] = Field(default_factory=list)
    components: list[RuleItem] = Field(default_factory=list)
    accessibility: list[RuleItem] = Field(default_factory=list)
    color_usage: list[RuleItem] = Field(default_factory=list)
    typography_usage: list[RuleItem] = Field(default_factory=list)
    misc_rules: list[RuleItem] = Field(default_factory=list)
    images: list[ImageItem] = Field(default_factory=list)
    fonts_detected: list[FontUsage] = Field(default_factory=list)
    stats: ProfileStats = Field(default_factory=ProfileStats)

    def all_rules(self) -> list[RuleItem]:
        return [r for cat in RULE_CATEGORIES for r in getattr(self, cat)]
