"""Deterministic comparison checks: colors (CIEDE2000), contrast (WCAG), typography, phrase rules
mined from the reference ("avoid X", "never Y"), and a visual logo-background heuristic."""

import difflib
import math
import re
from itertools import count

from stylelens.colors import ciede2000, contrast_ratio, find_colors, hex_to_lab, wcag_level
from stylelens.compare.cite import VersionIndex
from stylelens.compare.schema import FindingModel, finding_category
from stylelens.config import get_settings
from stylelens.extraction.common import NEG_RE, clauses
from stylelens.schema.profile import ColorItem, RuleItem, StyleProfile, TypographyItem

_ids = count(1)


def fid(prefix: str) -> str:
    return f"{prefix}-{next(_ids):03d}"


def reset_ids() -> None:
    global _ids
    _ids = count(1)


def _refs(item) -> list[dict]:
    return [r.model_dump() for r in item.source_refs]


def _name_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    a, b = a.lower(), b.lower()
    if a.split()[0] == b.split()[0] or a.split()[-1] == b.split()[-1] and len(a.split()) > 1:
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def _is_neutral_extreme(hex_: str) -> bool:
    L, a, b = hex_to_lab(hex_)
    return math.hypot(a, b) < 3 and (L > 97 or L < 3)


def _label(c: ColorItem) -> str:
    return f"{c.name} {c.hex}" if c.name else c.hex


def check_colors(ref: StyleProfile, cand: StyleProfile, ri: VersionIndex, ci: VersionIndex,
                 guide_like: bool) -> list[FindingModel]:
    s = get_settings()
    out: list[FindingModel] = []
    approved = [c for c in ref.colors if c.status == "approved"]
    prohibited = [c for c in ref.colors if c.status == "prohibited"]
    palette_rule = next((r for r in ref.color_usage if r.polarity == "dont" and re.search(
        r"outside (this|the) palette|introduce|off-palette|only (use )?(the|our) palette|new colou?rs", r.statement, re.I)), None)

    matched_ref: set[str] = set()
    for c in cand.colors:
        if c.status != "approved":
            continue
        cand_cites = ci.cite_refs(_refs(c), limit=2)
        if not cand_cites:
            continue
        lab = hex_to_lab(c.hex)
        nearest = min(approved, key=lambda r: (ciede2000(lab, hex_to_lab(r.hex)), r.hex), default=None)
        de = ciede2000(lab, hex_to_lab(nearest.hex)) if nearest else 999
        base = {"candidate_hex": c.hex, "candidate_name": c.name}
        if nearest and de <= s.delta_e_exact:
            matched_ref.add(nearest.id)
            out.append(FindingModel(
                finding_id=fid("color"), category="colors", status="compliant", severity="info",
                summary=f"{_label(c)} matches the guide's {_label(nearest)} (ΔE {de:.2f}).",
                reasoning="Exact match within the configured tolerance.",
                reference_citations=ri.cite_refs(_refs(nearest)), candidate_citations=cand_cites, confidence=0.99,
                data={**base, "reference_hex": nearest.hex, "delta_e": round(de, 2), "match": "exact"}))
            continue
        if nearest and de <= s.delta_e_near:
            matched_ref.add(nearest.id)
            out.append(FindingModel(
                finding_id=fid("color"), category="colors", status="deviation", severity="minor",
                summary=f"{_label(c)} is a near match for {_label(nearest)} (ΔE {de:.2f}); use the exact value.",
                reasoning=f"Perceptual difference ΔE2000 = {de:.2f} is below the near-match threshold "
                          f"({s.delta_e_near}) but above an exact match ({s.delta_e_exact}).",
                reference_citations=ri.cite_refs(_refs(nearest)), candidate_citations=cand_cites, confidence=0.95,
                data={**base, "reference_hex": nearest.hex, "delta_e": round(de, 2), "match": "near"}))
            continue
        banned = next((p for p in prohibited if ciede2000(lab, hex_to_lab(p.hex)) <= s.delta_e_near), None)
        if banned:
            out.append(FindingModel(
                finding_id=fid("color"), category="colors", status="conflict", severity="critical",
                summary=f"{_label(c)} is a color the guide prohibits.",
                reasoning=f"The reference explicitly prohibits {banned.hex}.",
                reference_citations=ri.cite_refs(_refs(banned)), candidate_citations=cand_cites, confidence=0.95,
                data={**base, "reference_hex": banned.hex}))
            continue
        if _is_neutral_extreme(c.hex):
            continue
        by_name = max(approved, key=lambda r: (_name_similarity(c.name, r.name), r.hex), default=None)
        if by_name and (_name_similarity(c.name, by_name.name) >= 0.72 or (c.role == "primary" == by_name.role)):
            d2 = ciede2000(lab, hex_to_lab(by_name.hex))
            matched_ref.add(by_name.id)
            out.append(FindingModel(
                finding_id=fid("color"), category="colors", status="deviation", severity="major",
                summary=f"{_label(c)} doesn't match the guide's {_label(by_name)} (ΔE {d2:.1f}).",
                reasoning="Same name or role as a reference color, but the value is perceptibly different.",
                reference_citations=ri.cite_refs(_refs(by_name)), candidate_citations=cand_cites, confidence=0.9,
                data={**base, "reference_hex": by_name.hex, "delta_e": round(d2, 2), "match": "name"}))
            continue
        if palette_rule:
            out.append(FindingModel(
                finding_id=fid("color"), category="colors", status="conflict", severity="major",
                summary=f"{_label(c)} is outside the approved palette.",
                reasoning=f"Nearest palette color is {_label(nearest)} (ΔE {de:.1f}); the guide forbids colors "
                          "outside its palette." if nearest else "The guide forbids colors outside its palette.",
                reference_citations=ri.cite_refs(_refs(palette_rule)), candidate_citations=cand_cites,
                confidence=0.9, data={**base, "delta_e": round(de, 2), "nearest_hex": nearest.hex if nearest else None}))
        else:
            out.append(FindingModel(
                finding_id=fid("color"), category="colors", status="new", severity="minor",
                summary=f"{_label(c)} is not part of the reference palette.",
                reasoning=f"Nearest palette color is {_label(nearest)} (ΔE {de:.1f})." if nearest else "",
                candidate_citations=cand_cites, confidence=0.85, data={**base, "delta_e": round(de, 2)}))

    if guide_like:
        for r in approved:
            if r.id in matched_ref or r.role not in ("primary", "secondary", "accent", "background", "text"):
                continue
            if any(ciede2000(hex_to_lab(c.hex), hex_to_lab(r.hex)) <= s.delta_e_near for c in cand.colors):
                continue
            cites = ri.cite_refs(_refs(r))
            if cites:
                out.append(FindingModel(
                    finding_id=fid("color"), category="colors", status="missing", severity="minor",
                    summary=f"The candidate palette omits the guide's {r.role} color {_label(r)}.",
                    reference_citations=cites, confidence=0.8, data={"reference_hex": r.hex}))
    return out


NAMED = {"white": "#FFFFFF", "black": "#000000"}


def check_contrast(ref: StyleProfile, cand: StyleProfile, ri: VersionIndex, ci: VersionIndex) -> list[FindingModel]:
    """Stated text/background pairs in the candidate ("… #A0A0A0 on white") checked against WCAG."""
    out: list[FindingModel] = []
    names = {**NAMED, **{c.name.lower(): c.hex for c in [*cand.colors, *ref.colors] if c.name}}
    req_rule = next((r for r in ref.accessibility if re.search(r"4\.5\s*:\s*1|contrast|wcag", r.statement, re.I)), None)
    name_re = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")\b", re.I)
    for el in ci.elements.values():
        if el.type not in ("paragraph", "list_item", "table") or " on " not in el.text:
            continue
        for cl in clauses(el.text):
            if " on " not in cl:
                continue
            mentions = [(m.span[0], m.hex) for m in find_colors(cl)]
            mentions += [(m.start(), names[m.group(1).lower()]) for m in name_re.finditer(cl)]
            mentions.sort()
            on_pos = cl.find(" on ")
            fg = [h for p, h in mentions if p < on_pos]
            bg = [h for p, h in mentions if p > on_pos]
            if not fg or not bg:
                continue
            ratio = contrast_ratio(fg[-1], bg[0])
            large = bool(re.search(r"\b(large|headline|heading|display|h1|h2)\b", cl, re.I))
            level = wcag_level(ratio, large)
            cand_cite = ci.cite_element(el.id, cl)
            if not cand_cite:
                continue
            if level == "fail":
                out.append(FindingModel(
                    finding_id=fid("contrast"), category="accessibility", status="deviation", severity="critical",
                    summary=f"{fg[-1]} on {bg[0]} has a contrast ratio of {ratio:.2f}:1, below WCAG AA "
                            f"({'3' if large else '4.5'}:1).",
                    reasoning="Computed with the WCAG 2.x relative-luminance formula.",
                    reference_citations=ri.cite_refs(_refs(req_rule)) if req_rule else [],
                    candidate_citations=[cand_cite], confidence=0.97,
                    data={"foreground": fg[-1], "background": bg[0], "ratio": round(ratio, 2), "wcag": level}))
            else:
                out.append(FindingModel(
                    finding_id=fid("contrast"), category="accessibility", status="compliant", severity="info",
                    summary=f"{fg[-1]} on {bg[0]} meets WCAG {level} ({ratio:.2f}:1).",
                    reference_citations=ri.cite_refs(_refs(req_rule)) if req_rule else [],
                    candidate_citations=[cand_cite], confidence=0.97,
                    data={"foreground": fg[-1], "background": bg[0], "ratio": round(ratio, 2), "wcag": level}))
    return out


HEAD = {"display", "headline", "title", "h1", "h2", "heading", "subhead"}
BODY = {"body", "text", "primary"}
SMALL = {"caption", "label"}


def _group(role: str) -> str:
    return "head" if role in HEAD else "small" if role in SMALL else "body" if role in BODY else role


def _px(size: str | None) -> float | None:
    if not size:
        return None
    m = re.match(r"([\d.]+)\s*(px|pt|rem|em)?", size)
    if not m:
        return None
    v = float(m.group(1))
    return v * {"pt": 1.333, "rem": 16, "em": 16}.get((m.group(2) or "px").lower(), 1)


def check_typography(ref: StyleProfile, cand: StyleProfile, ri: VersionIndex, ci: VersionIndex) -> list[FindingModel]:
    out: list[FindingModel] = []
    ref_families = {t.family.lower() for t in ref.typography} | {f.lower() for t in ref.typography for f in t.fallbacks}
    for t in cand.typography:
        cand_cites = ci.cite_refs(_refs(t))
        if not cand_cites:
            continue
        group = _group(t.role)
        peers: list[TypographyItem] = [r for r in ref.typography if _group(r.role) == group] or \
            [r for r in ref.typography if r.role == t.role]
        if not peers:
            if t.family.lower() not in ref_families and ref.typography:
                out.append(FindingModel(
                    finding_id=fid("type"), category="typography", status="new", severity="minor",
                    summary=f"{t.family} ({t.role}) isn't part of the guide's type system.",
                    candidate_citations=cand_cites, confidence=0.75, data={"family": t.family}))
            continue
        fams = {p.family.lower() for p in peers}
        best = next((p for p in peers if p.role == t.role), peers[0])
        if t.family.lower() not in fams:
            out.append(FindingModel(
                finding_id=fid("type"), category="typography", status="deviation", severity="major",
                summary=f"{t.role.title()} text uses {t.family}; the guide specifies "
                        f"{' / '.join(sorted({p.family for p in peers}))}.",
                reasoning=f"Typeface for the {group} role differs from the reference type system.",
                reference_citations=ri.cite_refs(_refs(best)), candidate_citations=cand_cites, confidence=0.92,
                data={"candidate_family": t.family, "reference_families": sorted({p.family for p in peers})}))
            continue
        same_role = next((p for p in peers if p.role == t.role and p.size), None)
        cs, rs = _px(t.size), _px(same_role.size if same_role else None)
        if cs and rs and abs(cs - rs) / rs > 0.08:
            out.append(FindingModel(
                finding_id=fid("type"), category="typography", status="deviation", severity="minor",
                summary=f"{t.role} size is {t.size}; the guide specifies {same_role.size}.",
                reference_citations=ri.cite_refs(_refs(same_role)), candidate_citations=cand_cites, confidence=0.9,
                data={"candidate_size": t.size, "reference_size": same_role.size}))
        else:
            out.append(FindingModel(
                finding_id=fid("type"), category="typography", status="compliant", severity="info",
                summary=f"{t.role.title()} uses {t.value}, consistent with the guide.",
                reference_citations=ri.cite_refs(_refs(best)), candidate_citations=cand_cites, confidence=0.85))

    # Size statements in candidate rules ("Captions may go down to 11px") vs reference sizes
    ref_sizes = {_group(r.role): (r, _px(r.size)) for r in sorted(ref.typography, key=lambda r: -(_px(r.size) or 0))
                 if _px(r.size)}
    ref_sizes.update({r.role: (r, _px(r.size)) for r in ref.typography if _px(r.size)})
    for rule in cand.all_rules():
        m = re.search(r"(\d+(?:\.\d+)?)\s?px", rule.statement)
        role = next((k for k in ("caption", "body", "label") if k in rule.statement.lower()), None)
        if not m or not role or role not in ref_sizes:
            continue
        ref_item, ref_px = ref_sizes[role]
        if float(m.group(1)) < ref_px * 0.95:
            cites = ci.cite_refs(_refs(rule))
            if cites:
                out.append(FindingModel(
                    finding_id=fid("type"), category="typography", status="deviation", severity="minor",
                    summary=f"Candidate allows {role} text at {m.group(1)}px; the guide sets {ref_item.size}.",
                    reference_citations=ri.cite_refs(_refs(ref_item)), candidate_citations=cites, confidence=0.85,
                    data={"candidate_size": f"{m.group(1)}px", "reference_size": ref_item.size}))
    return out


# -- phrase rules ---------------------------------------------------------------------------------
QUOTE_RE = re.compile(r"[\"“]([^\"”]{2,40})[\"”]")


def banned_patterns(ref: StyleProfile) -> list[tuple[re.Pattern, str, RuleItem]]:
    """Mine prohibited phrasings from the reference's own rules."""
    out: list[tuple[re.Pattern, str, RuleItem]] = []

    def add(phrase: str, rule: RuleItem):
        phrase = phrase.strip().strip(".,")
        if not phrase or len(phrase) < 2:
            return
        if re.fullmatch(r"\d+(st|nd|rd|th)", phrase):
            pat = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)\b")
            label = "ordinal date suffix"
        elif re.search(r"\d", phrase):
            # "4.50 USD" -> any amount followed by USD
            pat = re.compile(re.sub(r"\d+", r"\\d+", re.escape(phrase)))
            label = f'"{phrase}"-style formatting'
        else:
            pat = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.I if not phrase.isupper() else 0)
            label = f'"{phrase}"'
        out.append((pat, label, rule))

    for rule in ref.all_rules():
        text = rule.statement
        for m in re.finditer(r"(?:not|instead of|never|avoid|rather than)\s+[\"“]([^\"”]{2,40})[\"”]", text, re.I):
            add(m.group(1), rule)
        if rule.polarity == "dont":
            for cl in clauses(text):
                neg = NEG_RE.search(cl)
                if neg:
                    for q in QUOTE_RE.finditer(cl[neg.start():]):
                        add(q.group(1), rule)
    seen, uniq = set(), []
    for pat, label, rule in out:
        if pat.pattern not in seen:
            seen.add(pat.pattern)
            uniq.append((pat, label, rule))
    return uniq


def check_phrases(ref: StyleProfile, ri: VersionIndex, ci: VersionIndex) -> list[FindingModel]:
    out: list[FindingModel] = []
    patterns = banned_patterns(ref)
    caps_rule = next((r for r in ref.all_rules() if re.search(r"all caps|uppercase", r.statement, re.I)
                      and r.polarity == "dont"), None)
    excl_rule = next((r for r in ref.all_rules() if "exclamation" in r.statement.lower()), None)
    for el in sorted(ci.elements.values(), key=lambda e: e.seq):
        if el.type not in ("paragraph", "list_item", "heading", "table") or not el.text:
            continue
        hits: dict[str, tuple[RuleItem, list[str]]] = {}
        for pat, label, rule in patterns:
            for m in pat.finditer(el.text):
                # don't flag the candidate quoting the right form next to the wrong one
                hits.setdefault(rule.id, (rule, []))[1].append(m.group(0))
        if caps_rule:
            caps = re.findall(r"\b(?:[A-Z]{2,}\s+){2,}[A-Z]{2,}\b", el.text)
            if caps:
                hits.setdefault(caps_rule.id, (caps_rule, []))[1].extend(caps)
        if excl_rule and ("!" in el.text) and (el.type == "heading" or el.text.count("!") > 1):
            hits.setdefault(excl_rule.id, (excl_rule, []))[1].append("!" * min(el.text.count("!"), 3))
        for rule, found in hits.values():
            cand_cite = ci.cite_element(el.id, el.text)
            ref_cites = ri.cite_refs(_refs(rule))
            if not cand_cite or not ref_cites:
                continue
            uniq = list(dict.fromkeys(found))[:4]
            out.append(FindingModel(
                finding_id=fid("copy"), category=finding_category(rule.category), status="deviation",
                severity="major" if rule.normative_level == "must" else "minor",
                summary=f"Uses {', '.join(repr(u) for u in uniq)} — the guide says: {rule.statement}",
                reasoning="Matched a phrasing the reference explicitly rules out.",
                reference_citations=ref_cites, candidate_citations=[cand_cite], confidence=0.8,
                method="heuristic", data={"matches": uniq, "rule_id": rule.id}))
    return out


def check_logo_backgrounds(ref: StyleProfile, cand: StyleProfile, ri: VersionIndex, ci: VersionIndex) -> list[FindingModel]:
    """Visual heuristic: a logo image whose background is very busy (many distinct dominant colors)
    when the reference forbids busy/photographic logo backgrounds."""
    rule = next((r for r in ref.logo_rules if r.polarity == "dont" and re.search(r"busy|photo", r.statement, re.I)), None)
    if not rule:
        return []
    out = []
    for img in cand.images:
        if img.kind != "logo" and "logo" not in (img.caption or "").lower():
            continue
        cols = img.dominant_colors
        labs = [hex_to_lab(h) for h in cols]
        spread = (sum(ciede2000(a, b) for i, a in enumerate(labs) for b in labs[i + 1:])
                  / max(len(labs) * (len(labs) - 1) / 2, 1)) if len(labs) > 1 else 0
        busy = len(cols) >= 4 and spread > 25
        cite = ci.cite_element(img.element_id, img.caption or img.description)
        if not cite:
            continue
        if busy:
            out.append(FindingModel(
                finding_id=fid("logo"), category="logo_rules", status="deviation", severity="major",
                summary="The logo appears on a busy, multi-colored background.",
                reasoning=f"{len(cols)} distinct dominant colors (mean ΔE {spread:.0f}) suggest a photographic or "
                          "patterned background, which the guide prohibits for the logo.",
                reference_citations=ri.cite_refs(_refs(rule)), candidate_citations=[cite], confidence=0.6,
                method="visual", data={"dominant_colors": cols, "spread": round(spread, 1)}))
    return out
