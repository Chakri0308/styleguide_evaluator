"""Google Gemini via the official google-genai SDK.

Translates the internal Anthropic-shaped messages ({"role", "content": str | [blocks]}, base64 image
blocks) into Gemini contents, and strict JSON schemas into `response_json_schema` (with $refs inlined).
"""

import base64
import copy
from collections.abc import AsyncIterator

from stylelens.config import get_settings
from stylelens.llm.base import CallMeta, LLMRefusal, LLMResult, LLMUnavailable

_client = None


def client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def inline_refs(schema: dict) -> dict:
    """Gemini's schema support is a subset of JSON Schema; inline $defs/$ref to be safe."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
                return walk(target)
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def to_contents(messages: list[dict]) -> list:
    from google.genai import types

    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        parts = []
        for b in blocks:
            if b.get("type") == "image":
                src = b["source"]
                parts.append(types.Part.from_bytes(data=base64.b64decode(src["data"]), mime_type=src["media_type"]))
            elif b.get("text"):
                parts.append(types.Part.from_text(text=b["text"]))
        if parts:
            contents.append(types.Content(role=role, parts=parts))
    return contents


def _config(system: str, max_tokens: int, json_schema: dict | None):
    from google.genai import types

    kwargs = {"system_instruction": system, "max_output_tokens": max_tokens}
    if json_schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_json_schema"] = inline_refs(json_schema)
    return types.GenerateContentConfig(**kwargs)


def _check_blocked(response) -> None:
    fb = getattr(response, "prompt_feedback", None)
    if fb is not None and getattr(fb, "block_reason", None):
        raise LLMRefusal(f"Gemini blocked the request ({fb.block_reason}).")
    for cand in getattr(response, "candidates", None) or []:
        reason = str(getattr(cand, "finish_reason", "") or "")
        if any(r in reason for r in ("SAFETY", "PROHIBITED", "BLOCKLIST", "SPII")):
            raise LLMRefusal(f"Gemini stopped for safety reasons ({reason}).")


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str):
        self.model = model

    async def complete(self, *, system, messages, max_tokens, json_schema=None, effort=None,
                       meta: CallMeta | None = None) -> LLMResult:
        from google.genai import errors

        try:
            response = await client().aio.models.generate_content(
                model=self.model, contents=to_contents(messages), config=_config(system, max_tokens, json_schema))
        except errors.APIError as exc:
            raise LLMUnavailable(f"Gemini API error: {exc}") from exc
        _check_blocked(response)
        usage = response.usage_metadata.model_dump() if response.usage_metadata else {}
        finish = str(response.candidates[0].finish_reason) if response.candidates else None
        return LLMResult(text=response.text or "", model=f"gemini:{self.model}", stop_reason=finish, usage=usage)

    async def stream(self, *, system, messages, max_tokens, effort=None,
                     meta: CallMeta | None = None) -> AsyncIterator[str]:
        from google.genai import errors

        try:
            stream = await client().aio.models.generate_content_stream(
                model=self.model, contents=to_contents(messages), config=_config(system, max_tokens, None))
            async for chunk in stream:
                _check_blocked(chunk)
                if chunk.text:
                    yield chunk.text
        except errors.APIError as exc:
            raise LLMUnavailable(f"Gemini API error: {exc}") from exc
