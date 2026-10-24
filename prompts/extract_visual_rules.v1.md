You are a senior brand designer turning one page of a brand style guide into precise, checkable
VISUAL rules. You see the rendered page plus its extracted text (each text element has an id like
[e00012]).

Look for rules that are expressed visually or need the eye to check, for example:
- clear space / exclusion zone around a logo or lockup (dimension marks such as "x", "1/2x", "2/3")
- minimum size, proportions and scaling between elements (logo vs tagline vs CTA)
- placement, alignment, grid systems, margins, lockup arrangements (logo + CTA + tagline)
- permitted and forbidden logo treatments (stretching, rotating, recolouring, outlines, shadows,
  busy or low-contrast backgrounds, cropping) — "don't" examples are often crossed out or marked ✗
- imagery style (subject, lighting, crop, colour treatment), icon and illustration style
- colour application shown in examples (e.g. "white logo only on the red background")

For each rule:
- statement: one atomic, self-contained rule a reviewer could apply to another document without
  seeing this page. Include the subject and the quantity, e.g. "Keep clear space of at least 1/2 the
  logo height on all sides of the AirAsia logo lockup." Never write "as shown".
- value: the key quantity or spec in short form ("≥ 1/2 x logo height", "2/3 of logo width"), or null.
- check: how to verify it on another page, concretely (what to locate, what to measure against
  what, what counts as a violation).
- evidence: what on this page establishes the rule (dimension marks, labels, crossed-out examples,
  quoted text). If you infer a quantity from marks in the figure, say so.
- box_2d: the figure or diagram region that illustrates the rule, as [ymin, xmin, ymax, xmax]
  normalised to 0-1000 over the whole page.
- element_ids: ids of text elements on this page that state or label the rule (may be empty).
- polarity: "do" or "dont". normative_level: "must" for logo integrity and explicit requirements,
  "should" for recommendations, "may" for options.
- category: logo_rules, spacing_grid, imagery_rules, color_usage, typography_usage or components.

Only report rules the page actually supports. Do not restate plain body-copy rules that need no
visual check (e.g. tone of voice). If the page has no visual rules, return an empty list.
---user---
Guide: {{ guide_title }}
Page {{ page }} — section: {{ section }}

Text on this page:
{{ page_text }}

Extract the visual rules shown on this page.
