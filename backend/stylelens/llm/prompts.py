"""Versioned prompt templates loaded from /prompts.

Each prompt lives in `prompts/<name>.v<N>.md` with a system part and a user part separated by a line
containing only `---user---`. Templates are Jinja2. The active version of every prompt is pinned in
PROMPT_VERSIONS so changing a prompt is an explicit, cache-busting change.
"""

from dataclasses import dataclass
from functools import lru_cache

from jinja2 import Environment, StrictUndefined

from stylelens.config import get_settings

PROMPT_VERSIONS: dict[str, int] = {
    "extract_rules": 1,
    "validate_colors": 1,
    "describe_image": 1,
    "rewrite_query": 1,
    "answer": 1,
    "verify_citations": 1,
    "judge_pair": 1,
    "judge_missing": 1,
    "suggest_followups": 1,
    "extract_visual_rules": 1,
    "detect_visual_subjects": 1,
    "visual_check": 1,
    "verify_visual": 1,
    "classify_rules": 1,
}

_env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=False,
                   trim_blocks=True, lstrip_blocks=True)


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    system: str
    user: str

    @property
    def id(self) -> str:
        return f"{self.name}.v{self.version}"


@lru_cache
def load(name: str) -> Prompt:
    version = PROMPT_VERSIONS[name]
    path = get_settings().prompts_dir / f"{name}.v{version}.md"
    raw = path.read_text()
    if "\n---user---\n" not in raw:
        raise ValueError(f"{path} is missing the ---user--- separator")
    system, user = raw.split("\n---user---\n", 1)
    return Prompt(name, version, system.strip(), user.strip())


def render(name: str, **variables) -> tuple[Prompt, str, str]:
    p = load(name)
    return p, _env.from_string(p.system).render(**variables), _env.from_string(p.user).render(**variables)
