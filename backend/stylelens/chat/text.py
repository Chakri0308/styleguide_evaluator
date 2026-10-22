import re

_ABBREV = re.compile(r"\b(e\.g|i\.e|etc|vs|a\.m|p\.m|fig|no)\.$", re.I)


def split_sentences(text: str) -> list[str]:
    """Split Markdown-ish text into sentences / list items. Citation markers that follow a sentence's
    final punctuation ("… colour. [2]") stay attached to that sentence."""
    out: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^([-*•]|\d+\.)\s+", "", line.strip())
        if not line:
            continue
        start = i = 0
        while i < len(line):
            if line[i] in ".!?":
                j = i + 1
                while j < len(line) and line[j] in " [":
                    if line[j] == "[":
                        k = line.find("]", j)
                        if k == -1:
                            break
                        j = k + 1
                    else:
                        j += 1
                at_end = j >= len(line)
                if (at_end or line[j].isupper() or line[j] in "\"“*") and not _ABBREV.search(line[start : i + 1]):
                    out.append(line[start:j].strip())
                    start = i = j
                    continue
            i += 1
        if line[start:].strip():
            out.append(line[start:].strip())
    return out
