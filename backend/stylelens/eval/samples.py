"""Sample documents for tests and the evaluation harness.

  * northwind_guide.pdf      — reference brand guide (coffee roaster)
  * lumen_guide.pdf          — reference design/writing guide (health app)
  * northwind_partner.pdf    — candidate style guide with seeded deviations/conflicts/omissions
  * northwind_flyer.pdf      — candidate marketing asset with seeded deviations
  * lumen_release_notes.md   — candidate copy (Markdown) with seeded writing deviations

Run `python -m stylelens.eval.samples OUT_DIR` to write them to disk.
"""

import sys
from pathlib import Path

from stylelens.eval.pdfkit import PdfBuilder, logo_png, photo_png

NORTHWIND_COLORS = [
    {"name": "Harbor Blue", "hex": "#1B4F9C", "rgb": "27, 79, 156", "cmyk": "100, 70, 0, 10", "pantone": "2945 C", "role": "primary"},
    {"name": "Roast", "hex": "#3B2A20", "rgb": "59, 42, 32", "cmyk": "40, 65, 75, 75", "pantone": "4975 C", "role": "text"},
    {"name": "Crema", "hex": "#F2E3C6", "rgb": "242, 227, 198", "cmyk": "4, 10, 24, 0", "pantone": "7506 C", "role": "background"},
    {"name": "Ember", "hex": "#D9622B", "rgb": "217, 98, 43", "cmyk": "0, 70, 90, 5", "pantone": "7579 C", "role": "accent"},
    {"name": "Sage", "hex": "#7A9A7E", "rgb": "122, 154, 126", "cmyk": "45, 15, 45, 5", "pantone": "556 C", "role": "secondary"},
    {"name": "Fog", "hex": "#E6E8EB", "rgb": "230, 232, 235", "cmyk": "8, 5, 4, 0", "pantone": "Cool Gray 1 C", "role": "neutral"},
]


def northwind_guide() -> bytes:
    b = PdfBuilder("Northwind Coffee Brand Guidelines")
    b.space(140)
    b.text("Northwind Coffee", size=40, font="hebo", leading=1.1)
    b.text("Brand Guidelines — Version 3.2", size=16, leading=1.6)
    b.p("This document is the single source of truth for how the Northwind Coffee brand looks, sounds and behaves. "
        "It applies to every channel: packaging, retail, web, social, email and partner co-marketing.")
    b.new_page()

    b.h1("1. Brand Foundations")
    b.h2("Mission")
    b.p("Northwind exists to make carefully sourced coffee feel welcoming, not exclusive. We roast in small batches "
        "in Portland and pay growers at least 25% above Fair Trade minimums.")
    b.h2("Brand Personality")
    b.bullets(["Warm — we sound like a friendly barista, not a corporation.",
               "Knowledgeable — we share expertise without showing off.",
               "Unhurried — we never create false urgency."])

    b.h1("2. Voice and Tone")
    b.p("Our voice stays the same everywhere; our tone adapts to the moment. Write the way you would explain coffee "
        "to a curious friend across the counter.")
    b.h3("Voice principles")
    b.bullets(["Plain-spoken: prefer short, concrete words. Say \"use\", not \"utilize\".",
               "Second person: address the reader as \"you\". Avoid \"customers\" or \"consumers\".",
               "Never hype: do not use superlatives such as \"best ever\", \"unbelievable\" or \"world-class\".",
               "Calm punctuation: avoid exclamation marks in headlines. At most one exclamation mark per piece of body copy.",
               "No shouting: never use ALL CAPS for emphasis. Use sentence case for headlines and buttons."])
    b.h3("Tone by context")
    b.table([["Context", "Tone", "Example"],
             ["Packaging", "Sensory, evocative", "Notes of cocoa and dried cherry."],
             ["Customer support", "Patient, direct", "Here's how to fix that."],
             ["Promotions", "Inviting, never pushy", "Try our new winter blend."],
             ["Errors", "Apologetic, helpful", "Sorry, that didn't work. Try again."]],
            col_widths=[130, 150, 220])

    b.h1("3. Color")
    b.p("Color is our most recognisable asset. Harbor Blue leads; Crema and Roast carry most layouts; Ember is an "
        "accent used sparingly for calls to action — never more than 10% of any layout.")
    b.h2("Primary and Secondary Palette")
    b.swatches(NORTHWIND_COLORS)
    b.h3("Color usage rules")
    b.bullets(["Harbor Blue (#1B4F9C) is the primary brand color and must appear on every brand touchpoint.",
               "Use Roast (#3B2A20) for body text on light backgrounds; never use pure black #000000 for text.",
               "Ember (#D9622B) is reserved for calls to action and must not be used for large background areas.",
               "Do not introduce colors outside this palette. Tints of palette colors in 20% steps are allowed.",
               "Never place Ember text on Harbor Blue; the combination fails contrast requirements."])
    b.h3("Approved color pairings")
    b.table([["Text", "Background", "Contrast", "Use"],
             ["Roast #3B2A20", "Crema #F2E3C6", "11.9:1", "Body copy"],
             ["White #FFFFFF", "Harbor Blue #1B4F9C", "8.1:1", "Buttons, headers"],
             ["Harbor Blue #1B4F9C", "Fog #E6E8EB", "6.6:1", "Links, UI"]],
            col_widths=[130, 150, 90, 130])

    b.h1("4. Typography")
    b.p("Our type system pairs a characterful serif for display with a highly legible sans for everything else.")
    b.h2("Typefaces")
    b.bullets(["Display: Fraunces Semibold (600). Used for headlines H1 and H2 only.",
               "Text: Inter Regular (400) and Inter Medium (500). Used for body copy, UI and H3 and below.",
               "Fallbacks: Georgia for Fraunces; Helvetica, Arial for Inter."])
    b.h2("Type Scale")
    b.table([["Style", "Typeface", "Size / Line height", "Letter spacing"],
             ["H1", "Fraunces Semibold", "48px / 56px", "-1%"],
             ["H2", "Fraunces Semibold", "32px / 40px", "-0.5%"],
             ["H3", "Inter Medium", "20px / 28px", "0"],
             ["Body", "Inter Regular", "16px / 24px", "0"],
             ["Caption", "Inter Regular", "12px / 16px", "+1%"]],
            col_widths=[80, 150, 150, 120])
    b.bullets(["Body text must never be set smaller than 14px on screen or 9pt in print.",
               "Use sentence case for all headings. Do not track out lowercase text.",
               "Left-align text. Never justify body copy."])

    b.h1("5. Logo")
    b.image(logo_png("#1B4F9C", "#F2E3C6", "NORTHWIND"), 240, 100, "Figure 1. The Northwind primary logo on white.")
    b.h2("Clear Space")
    b.p("Keep clear space around the logo equal to the height of the \"N\" in the wordmark on all sides. No text, "
        "graphics or edges may intrude into this space.")
    b.h2("Minimum Size")
    b.p("The full logo must never be reproduced smaller than 24px tall on screen or 12mm wide in print. Below this "
        "size use the circular N monogram.")
    b.h2("Logo Misuse")
    b.bullets(["Do not place the logo on busy photographic backgrounds; use a solid Crema or Harbor Blue field.",
               "Do not stretch, rotate, outline or add drop shadows to the logo.",
               "Do not recolor the logo outside of Harbor Blue, Roast, or white (reversed).",
               "Do not lock up the logo with partner logos without the approved co-branding divider."], marker="✗")
    b.image(logo_png("#1B4F9C", "#F2E3C6", "NORTHWIND", busy=True), 240, 100,
            "Figure 2. Don't: the logo placed on a busy photographic background.")

    b.h1("6. Photography and Imagery")
    b.bullets(["Show real people and real cafés in natural window light. No staged stock photography.",
               "Warm color grading that leans toward Crema highlights; avoid cold blue casts.",
               "Hands and process shots (pouring, grinding, roasting) are preferred over product-only shots.",
               "Never use AI-generated images of people."])
    b.image(photo_png("#F2E3C6", "#7A5A40"), 260, 140, "Figure 3. Do: warm, natural-light photography of real people.")

    b.h1("7. Writing Style")
    b.h3("Grammar and mechanics")
    b.bullets(["Use the serial (Oxford) comma: \"beans, filters, and mugs\".",
               "Write dates as \"March 4, 2025\". Do not use ordinal suffixes like \"4th\".",
               "Use numerals for 10 and above; spell out one through nine.",
               "Prices: \"$4.50\", never \"4.50 USD\" in consumer copy.",
               "Coffee origins are capitalised (Ethiopia Yirgacheffe); roast levels are not (medium roast)."])
    b.h3("Words we use and avoid")
    b.table([["Use", "Avoid"], ["coffee lovers, you", "consumers, customers"], ["small-batch", "artisanal"],
             ["single origin", "premium"], ["roasted on", "best before"]], col_widths=[250, 250])

    b.h1("8. Accessibility")
    b.bullets(["All text must meet WCAG 2.2 AA contrast: 4.5:1 for body text and 3:1 for large text (24px+).",
               "Never convey meaning with color alone; pair color with text or icons.",
               "Every image needs descriptive alt text written in our voice.",
               "Interactive targets must be at least 44 by 44 px."])

    b.h1("9. UI Components")
    b.h3("Buttons")
    b.bullets(["Primary buttons: Harbor Blue fill, white Inter Medium 16px label, 8px corner radius.",
               "Call-to-action buttons may use Ember fill with white label; at most one per screen.",
               "Button labels are verbs in sentence case: \"Add to cart\", not \"ADD TO CART\"."])
    b.h3("Spacing and grid")
    b.bullets(["Use an 8px spacing scale (8, 16, 24, 32, 48, 64).",
               "Web layouts use a 12-column grid with 24px gutters and a 1200px max width."])
    return b.save()


LUMEN_COLORS = [
    {"name": "Lumen Teal", "hex": "#0F766E", "rgb": "15, 118, 110", "role": "primary"},
    {"name": "Midnight", "hex": "#0B1F33", "rgb": "11, 31, 51", "role": "text"},
    {"name": "Mist", "hex": "#F1F5F9", "rgb": "241, 245, 249", "role": "background"},
    {"name": "Coral Alert", "hex": "#E11D48", "rgb": "225, 29, 72", "role": "error"},
]


def lumen_guide() -> bytes:
    b = PdfBuilder("Lumen Health Design & Content Guide")
    b.text("Lumen Health", size=34, font="hebo", leading=1.2)
    b.text("Design & Content Guide", size=16, leading=1.8)
    b.h1("Principles")
    b.bullets(["Clarity over cleverness: patients read our screens when they are anxious.",
               "Calm confidence: we are reassuring, never alarming.",
               "Inclusive by default: design for low vision, low bandwidth and low literacy."])
    b.h1("Color")
    b.swatches(LUMEN_COLORS)
    b.bullets(["Lumen Teal is used for primary actions and navigation.",
               "Coral Alert (#E11D48) is only for errors and critical alerts — never for marketing.",
               "Backgrounds are Mist or white; dark mode uses Midnight surfaces."])
    b.h1("Typography")
    b.bullets(["Typeface: Source Sans 3 for all UI and content; weights 400, 600 and 700.",
               "Minimum body size is 17px on mobile to support older patients.",
               "Line height for body text is 1.5."])
    b.h1("Content Style")
    b.h3("Reading level")
    b.p("Write at or below an 8th-grade reading level. Prefer sentences under 20 words.")
    b.h3("Medical language")
    b.bullets(["Use plain words first, then the clinical term in parentheses: \"high blood pressure (hypertension)\".",
               "Never give a diagnosis in product copy. Say \"talk to your care team\".",
               "Do not use fear-based language such as \"deadly\" or \"dangerous\" in reminders."])
    b.h3("Mechanics")
    b.bullets(["Use sentence case for headings, buttons and labels.",
               "Use contractions (you're, we'll) to sound human.",
               "Write times as \"9:30 a.m.\" with lowercase a.m. and p.m."])
    b.h1("Accessibility")
    b.bullets(["All UI meets WCAG 2.2 AA; critical flows target AAA contrast (7:1).",
               "Touch targets are at least 48 by 48 px.",
               "Support dynamic type up to 200% without loss of content."])
    b.h1("Iconography")
    b.bullets(["Use the Lumen outline icon set at 1.5px stroke on a 24px grid.",
               "Icons always pair with a text label in navigation."])
    return b.save()


def northwind_partner_guide() -> bytes:
    """Candidate style guide written by a partner agency, with seeded issues (see golden/compare.json)."""
    b = PdfBuilder("Northwind x Fieldhouse Co-Marketing Style Guide")
    b.text("Northwind x Fieldhouse", size=30, font="hebo", leading=1.2)
    b.text("Co-marketing Style Guide (Agency draft)", size=14, leading=1.8)
    b.h1("Voice")
    b.bullets(["Energetic and bold! Use exclamation marks to create excitement in headlines.",
               "Use ALL CAPS for key offers to grab attention.",
               "Address the reader as \"you\"."])
    b.h1("Colors")
    b.swatches([
        {"name": "Northwind Blue", "hex": "#1D51A0", "rgb": "29, 81, 160", "role": "primary"},
        {"name": "Roast", "hex": "#3B2A20", "rgb": "59, 42, 32", "role": "text"},
        {"name": "Cream", "hex": "#E8C9A0", "rgb": "232, 201, 160", "role": "background"},
        {"name": "Fieldhouse Orange", "hex": "#FF5A1F", "rgb": "255, 90, 31", "role": "accent"},
    ])
    b.bullets(["Fieldhouse Orange may be used as a full-bleed background for promotional banners.",
               "Body text may be set in light gray #A0A0A0 on white for a modern look."])
    b.h1("Typography")
    b.bullets(["Headlines: Montserrat Bold, 44px, all caps.",
               "Body: Inter Regular 16px / 24px.",
               "Captions may go down to 11px."])
    b.h1("Logo")
    b.bullets(["The Northwind logo may be placed over lifestyle photography for energy.",
               "Minimum logo height is 16px on screen.",
               "Keep clear space equal to the height of the \"N\" around the logo."])
    b.h1("Writing")
    b.bullets(["Do not use the Oxford comma: \"beans, filters and mugs\".",
               "Dates are written as \"March 4th, 2025\".",
               "Use numerals for 10 and above; spell out one through nine."])
    return b.save()


def northwind_flyer() -> bytes:
    b = PdfBuilder("Winter Blend Launch Flyer", text_color="#000000")
    b.text("THE BEST WINTER COFFEE EVER!!!", size=28, font="hebo", leading=1.3)
    b.p("Unbelievable flavor for discerning consumers. Our world-class artisanal roasters have crafted a premium blend "
        "that you simply must try! Available from December 1st at all locations for 4.50 USD.")
    b.image(logo_png("#1B4F9C", "#F2E3C6", "NORTHWIND", busy=True), 240, 100, "Northwind logo over cafe photo")
    b.swatches([{"name": "Promo Orange", "hex": "#FF5A1F", "role": "accent"},
                {"name": "Harbor Blue", "hex": "#1B4F9C", "role": "primary"}])
    b.p("Visit northwind.coffee to order beans, filters and mugs today.")
    return b.save()


LUMEN_RELEASE_NOTES = """# What's New In Lumen 4.2

## Smarter Medication Reminders

Missing your hypertension medication is DANGEROUS and can be deadly! Lumen 4.2 now sends reminders at 9:30 AM by default.

## Improved Accessibility

- Touch targets are now 40 by 40 px for a cleaner look.
- Dynamic type is supported up to 150%.

## Diagnosis Assistant

Based on your symptoms, Lumen will tell you whether you have the flu. You are not required to consult your care team.
"""


def build_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "northwind_guide.pdf": northwind_guide(),
        "lumen_guide.pdf": lumen_guide(),
        "northwind_partner.pdf": northwind_partner_guide(),
        "northwind_flyer.pdf": northwind_flyer(),
        "lumen_release_notes.md": LUMEN_RELEASE_NOTES.encode(),
    }
    paths = {}
    for name, data in files.items():
        path = out_dir / name
        path.write_bytes(data)
        paths[name] = path
    return paths


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
    for name, path in build_all(out).items():
        print(f"{name}: {path.stat().st_size} bytes")
