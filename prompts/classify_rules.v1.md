You route the rules of a brand style guide to the right checker. A candidate document will be
checked against every rule: text rules by reading its text, visual rules by a reviewer LOOKING at its
rendered pages (logos, colours, type, photos, layout).

For each rule decide:
- mode:
  - "visual": can only be verified by looking (logo colour/treatment/placement/clear space, colour
    of elements, typefaces and weights as rendered, imagery style, layout, contrast as seen).
    Example: "Never reproduce the logo in yellow." → visual.
  - "text": verified from the words alone (tone, spelling, terminology, date formats, punctuation).
  - "both": has a visual and a textual side (e.g. "CTA buttons say 'Book now' in white on red").
- subject: what to look at on the page: logo, imagery, typography, color or layout ("text" for
  text-mode rules).
- check: for visual/both rules, one concrete instruction for the reviewer: what to locate on the
  page and what counts as a violation, e.g. "Find every AirAsia logo; flag any rendered in yellow or
  a yellow-dominant colour." null for text rules.

Return one entry per rule id, in the same order.
---user---
Guide: {{ guide_title }}

Rules:
{{ rules }}
