"""Deterministic offline provider for tests and keyless local runs.

JSON calls are answered by handlers registered per prompt name; unregistered prompts get the
smallest valid instance of the schema. Streaming answers quote the first context passage.
"""

import json
import re
from collections.abc import AsyncIterator, Callable

from stylelens.llm.base import CallMeta, LLMResult

Handler = Callable[[CallMeta, list[dict]], dict | str]
HANDLERS: dict[str, Handler] = {}


def register(prompt: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[prompt] = fn
        return fn

    return deco


def minimal_instance(schema: dict, defs: dict | None = None) -> object:
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return minimal_instance(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        options = schema["anyOf"]
        if any(o.get("type") == "null" for o in options):
            return None
        return minimal_instance(options[0], defs)
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object":
        return {k: minimal_instance(v, defs) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return []
    if t == "string":
        return ""
    if t in ("number", "integer"):
        return 0
    if t == "boolean":
        return False
    return None


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m["role"] != "user":
            continue
        if isinstance(m["content"], str):
            return m["content"]
        return "\n".join(b.get("text", "") for b in m["content"] if b.get("type") == "text")
    return ""


class FakeProvider:
    name = "fake"

    def __init__(self, model: str = "fake"):
        self.model = model

    async def complete(self, *, system, messages, max_tokens, json_schema=None, effort=None,
                       meta: CallMeta | None = None) -> LLMResult:
        meta = meta or CallMeta()
        handler = HANDLERS.get(meta.prompt)
        if handler is not None:
            out = handler(meta, messages)
            text = out if isinstance(out, str) else json.dumps(out)
        elif json_schema is not None:
            text = json.dumps(minimal_instance(json_schema))
        else:
            text = _last_user_text(messages)[:200]
        return LLMResult(text=text, model=f"fake:{self.model}", stop_reason="end_turn")

    async def stream(self, *, system, messages, max_tokens, effort=None,
                     meta: CallMeta | None = None) -> AsyncIterator[str]:
        meta = meta or CallMeta()
        handler = HANDLERS.get(meta.prompt)
        if handler is not None:
            out = handler(meta, messages)
            text = out if isinstance(out, str) else json.dumps(out)
        else:
            text = fake_grounded_answer(_last_user_text(messages))
        for token in re.findall(r"\S+\s*", text):
            yield token


def fake_grounded_answer(prompt: str) -> str:
    """Answer by quoting the first numbered source in the prompt, citing it."""
    m = re.search(r'<source id="(\d+)"[^>]*>\s*(.+?)</source>', prompt, re.S)
    if not m:
        return "The guide doesn't cover this."
    first_sentence = re.split(r"(?<=[.!?])\s", m.group(2).strip())[0]
    return f"According to the guide, {first_sentence} [{m.group(1)}]"
