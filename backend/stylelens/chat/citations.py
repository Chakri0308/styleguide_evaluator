"""Citation parsing and verification.

Every [n] in an answer must (1) refer to a source that was actually provided and exists in the index,
and (2) be supported by that source's text. Support is checked lexically (content-word overlap and
exact values such as hex codes / sizes must appear in the source), then — when an LLM is available —
confirmed per claim by a verifier model. Unsupported citations are flagged, invalid ones dropped.
"""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from stylelens.chat.text import split_sentences
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import generate_json, llm_available
from stylelens.retrieval.context import Source
from stylelens.retrieval.models import _stem, tokens

CITE_RE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
VALUE_RE = re.compile(r"#[0-9a-fA-F]{3,6}\b|\d+(?:\.\d+)?\s?(?:px|pt|mm|%|:1)|\b\d{2,}\b")


@dataclass
class ClaimCheck:
    sentence: str
    numbers: list[int]
    supported: bool
    reason: str = ""


@dataclass
class Verification:
    used: list[int]
    invalid: list[int]
    claims: list[ClaimCheck] = field(default_factory=list)

    def unsupported_numbers(self) -> set[int]:
        bad = set()
        for c in self.claims:
            if not c.supported:
                bad.update(c.numbers)
        ok = {n for c in self.claims if c.supported for n in c.numbers}
        return bad - ok


def cited_numbers(text: str) -> list[int]:
    out: list[int] = []
    for m in CITE_RE.finditer(text):
        for part in m.group(1).split(","):
            n = int(part.strip())
            if n not in out:
                out.append(n)
    return out


def strip_invalid(text: str, valid: set[int]) -> str:
    def fix(m: re.Match) -> str:
        nums = [p.strip() for p in m.group(1).split(",") if int(p.strip()) in valid]
        return f"[{', '.join(nums)}]" if nums else ""

    return CITE_RE.sub(fix, text)


def lexical_support(sentence: str, source_text: str) -> tuple[bool, str]:
    clean = CITE_RE.sub("", sentence)
    src_low = source_text.lower()
    for v in VALUE_RE.findall(clean):
        if v.lower().replace(" ", "") not in src_low.replace(" ", ""):
            return False, f"value {v!r} not found in source"
    words = {_stem(t) for t in tokens(clean) if len(t) > 2}
    if not words:
        return True, "no content words"
    src = {_stem(t) for t in tokens(source_text)}
    overlap = len(words & src) / len(words)
    return overlap >= 0.25, f"word overlap {overlap:.0%}"


class Verdict(BaseModel):
    index: int
    supported: bool
    reason: str


class Verdicts(BaseModel):
    verdicts: list[Verdict]


async def verify(answer: str, sources: dict[int, Source], use_llm: bool = True) -> Verification:
    used = cited_numbers(answer)
    invalid = [n for n in used if n not in sources]
    claims: list[ClaimCheck] = []
    for sentence in split_sentences(answer):
        nums = [n for n in cited_numbers(sentence) if n in sources]
        if not nums:
            continue
        joined = "\n".join(sources[n].text for n in nums)
        ok, reason = lexical_support(sentence, joined)
        claims.append(ClaimCheck(sentence=CITE_RE.sub("", sentence).strip(), numbers=nums, supported=ok, reason=reason))

    if use_llm and claims and llm_available("fast"):
        try:
            out = await generate_json(
                "fast", "verify_citations", Verdicts, max_tokens=2000,
                claims=[{"sentence": c.sentence, "n": ",".join(map(str, c.numbers)),
                         "source": "\n".join(sources[n].text for n in c.numbers)[:2500]} for c in claims])
            for v in out.verdicts:
                if 0 <= v.index < len(claims):
                    # A value mismatch found lexically is decisive; otherwise trust the verifier.
                    if not claims[v.index].reason.startswith("value"):
                        claims[v.index].supported = v.supported
                        claims[v.index].reason = v.reason
        except (LLMUnavailable, LLMRefusal, ValueError):
            pass
    return Verification(used=[n for n in used if n in sources], invalid=invalid, claims=claims)
