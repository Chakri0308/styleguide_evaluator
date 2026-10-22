"""Common parser interface. Every format parser returns a ParsedDocument of layout elements."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

# Element types shared by all parsers
TITLE = "title"
HEADING = "heading"
PARAGRAPH = "paragraph"
LIST_ITEM = "list_item"
TABLE = "table"
IMAGE = "image"
CAPTION = "caption"
SWATCH = "swatch"  # a filled vector shape (often a colour chip) in a PDF
CODE = "code"

ProgressFn = Callable[[float, str], None]


@dataclass
class ParsedElement:
    type: str
    text: str
    page: int = 1
    bbox: tuple[float, float, float, float] | None = None
    level: int | None = None  # heading level (1 = top)
    meta: dict = field(default_factory=dict)
    image: bytes | None = None  # raw image bytes for IMAGE elements
    image_ext: str = "png"


@dataclass
class ParsedPage:
    page: int
    width: float
    height: float
    render: bytes | None = None  # PNG preview


@dataclass
class ParsedDocument:
    parser: str
    title: str | None
    pages: list[ParsedPage]
    elements: list[ParsedElement]
    meta: dict = field(default_factory=dict)


class Parser(Protocol):
    name: str

    def parse(self, data: bytes, filename: str, progress: ProgressFn) -> ParsedDocument: ...


def assign_heading_paths(elements: list[ParsedElement]) -> list[list[str]]:
    """Compute the heading path (e.g. ['Brand', 'Color', 'Secondary']) for every element."""
    stack: list[tuple[int, str]] = []
    paths: list[list[str]] = []
    for el in elements:
        if el.type in (HEADING, TITLE):
            level = el.level if el.level is not None else 1
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, el.text.strip()[:200]))
            paths.append([t for _, t in stack])
        else:
            paths.append([t for _, t in stack])
    return paths


def noop_progress(_: float, __: str) -> None:
    pass
