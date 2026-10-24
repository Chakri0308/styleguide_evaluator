"""High-level LLM helpers: role-based model selection, versioned prompts, schema-validated JSON with
retry, and a content-addressed response cache for run-to-run consistency."""

import base64
import hashlib
import json
import logging
from collections.abc import AsyncIterator

from pydantic import BaseModel, ValidationError
from sqlalchemy.dialects.postgresql import insert

from stylelens.config import get_settings
from stylelens.db.models import CacheEntry
from stylelens.db.session import SessionLocal
from stylelens.llm import prompts
from stylelens.llm.base import CallMeta, LLMUnavailable, Provider

log = logging.getLogger(__name__)

ROLES = ("generation", "extraction", "vision", "fast")


def model_spec(role: str) -> str:
    s = get_settings()
    return {
        "generation": s.llm_generation_model,
        "extraction": s.llm_extraction_model,
        "vision": s.llm_vision_model,
        "fast": s.llm_fast_model,
    }[role]


def get_provider(role: str) -> Provider:
    spec = model_spec(role)
    provider, _, model = spec.partition(":")
    if provider == "anthropic":
        if not get_settings().anthropic_api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        from stylelens.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model)
    if provider == "gemini":
        if not get_settings().gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not set")
        from stylelens.llm.gemini_provider import GeminiProvider

        return GeminiProvider(model or "gemini-flash-latest")
    if provider == "fake":
        from stylelens.llm.fake_provider import FakeProvider

        return FakeProvider(model or "fake")
    raise LLMUnavailable(f"Unknown LLM provider '{provider}'")


def llm_available(role: str = "generation") -> bool:
    try:
        get_provider(role)
        return True
    except LLMUnavailable:
        return False


# -- cache ----------------------------------------------------------------------------------------
def cache_key(namespace: str, *parts) -> str:
    h = hashlib.sha256(namespace.encode())
    for p in parts:
        h.update(b"\x00")
        h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True, default=str).encode())
    return h.hexdigest()


async def cache_get(key: str) -> dict | None:
    async with SessionLocal() as session:
        row = await session.get(CacheEntry, key)
        return row.value if row else None


async def cache_put(key: str, namespace: str, value: dict) -> None:
    async with SessionLocal() as session:
        stmt = insert(CacheEntry).values(key=key, namespace=namespace, value=value)
        await session.execute(stmt.on_conflict_do_nothing(index_elements=["key"]))
        await session.commit()


# -- schema ---------------------------------------------------------------------------------------
def strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic JSON schema → strict structured-output schema (closed objects, all fields required)."""
    schema = model.model_json_schema()

    def fix(node):
        if isinstance(node, dict):
            node.pop("title", None)
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for key in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"):
                node.pop(key, None)
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(schema)
    return schema


def image_block(data: bytes, media_type: str = "image/png") -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                        "data": base64.standard_b64encode(data).decode()}}


# -- calls ----------------------------------------------------------------------------------------
async def generate_json[T: BaseModel](
    role: str,
    prompt_name: str,
    schema: type[T],
    *,
    images: list[tuple[bytes, str]] | None = None,
    max_tokens: int = 8000,
    effort: str | None = "low",
    use_cache: bool = True,
    retries: int = 2,
    **variables,
) -> T:
    provider = get_provider(role)
    prompt, system, user = prompts.render(prompt_name, **variables)
    json_schema = strict_schema(schema)
    key = cache_key("json", provider.name, provider.model, prompt.id, system, user, json_schema,
                    [hashlib.sha256(img).hexdigest() for img, _ in images or []])
    if use_cache and (hit := await cache_get(key)) is not None:
        return schema.model_validate(hit)

    content: list[dict] = [image_block(img, mt) for img, mt in images or []]
    content.append({"type": "text", "text": user})
    messages = [{"role": "user", "content": content}]
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        result = await provider.complete(system=system, messages=messages, max_tokens=max_tokens,
                                         json_schema=json_schema, effort=effort,
                                         meta=CallMeta(prompt=prompt_name, variables=variables))
        try:
            parsed = schema.model_validate_json(result.text)
        except ValidationError as exc:
            last_error = exc
            log.warning("%s attempt %d returned invalid JSON: %s", prompt.id, attempt + 1, exc)
            messages = messages[:1] + [
                {"role": "assistant", "content": result.text or "{}"},
                {"role": "user", "content": f"That output failed validation:\n{exc}\nReturn corrected JSON only."},
            ]
            continue
        if use_cache:
            await cache_put(key, "json", parsed.model_dump(mode="json"))
        return parsed
    raise ValueError(f"{prompt.id}: could not obtain valid JSON") from last_error


async def generate_text(role: str, prompt_name: str, *, max_tokens: int = 4000, effort: str | None = "low",
                        use_cache: bool = True, **variables) -> str:
    provider = get_provider(role)
    prompt, system, user = prompts.render(prompt_name, **variables)
    key = cache_key("text", provider.name, provider.model, prompt.id, system, user)
    if use_cache and (hit := await cache_get(key)) is not None:
        return hit["text"]
    result = await provider.complete(system=system, messages=[{"role": "user", "content": user}],
                                     max_tokens=max_tokens, effort=effort,
                                     meta=CallMeta(prompt=prompt_name, variables=variables))
    if use_cache:
        await cache_put(key, "text", {"text": result.text})
    return result.text


async def stream_text(role: str, prompt_name: str, *, history: list[dict] | None = None,
                      max_tokens: int = 16000, effort: str | None = "medium",
                      **variables) -> tuple[str, AsyncIterator[str], str]:
    """Returns (model id, token iterator, prompt id). Callers cache the full answer themselves."""
    provider = get_provider(role)
    prompt, system, user = prompts.render(prompt_name, **variables)
    messages = [*(history or []), {"role": "user", "content": user}]
    it = provider.stream(system=system, messages=messages, max_tokens=max_tokens, effort=effort,
                         meta=CallMeta(prompt=prompt_name, variables=variables))
    return f"{provider.name}:{provider.model}", it, prompt.id
