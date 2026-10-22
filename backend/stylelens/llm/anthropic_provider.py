"""Claude via the official Anthropic SDK.

Notes:
  * Sampling parameters (temperature/top_p/top_k) are not sent: current models only accept the
    defaults and API version 2026-10-21 rejects them. Run-to-run consistency comes from the
    response cache (see llm.client) and deterministic retrieval instead.
  * Thinking is adaptive (always on for Opus 5.5); depth is controlled with output_config.effort.
  * Server-side refusal fallback (`fallbacks: "default"`) is enabled unless LLM_REFUSAL_FALLBACK=off.
"""

from collections.abc import AsyncIterator

import anthropic

from stylelens.config import get_settings
from stylelens.llm.base import CallMeta, LLMRefusal, LLMResult

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that support the server-side `fallbacks: "default"` parameter.
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1")

_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        s = get_settings()
        _client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key or None, max_retries=3)
    return _client


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str):
        self.model = model

    def _params(self, system: str, messages: list[dict], max_tokens: int, effort: str | None,
                json_schema: dict | None = None) -> tuple[dict, bool]:
        params: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        output_config: dict = {}
        if effort:
            output_config["effort"] = effort
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}
        if output_config:
            params["output_config"] = output_config
        use_beta = get_settings().llm_refusal_fallback != "off" and self.model in _FALLBACK_MODELS
        if use_beta:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params, use_beta

    async def complete(self, *, system, messages, max_tokens, json_schema=None, effort=None,
                       meta: CallMeta | None = None) -> LLMResult:
        params, beta = self._params(system, messages, max_tokens, effort, json_schema)
        api = client().beta.messages if beta else client().messages
        if not beta:
            params.pop("betas", None)
        # Stream under the hood so long generations never hit HTTP timeouts.
        async with api.stream(**params) as stream:
            message = await stream.get_final_message()
        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            raise LLMRefusal(getattr(details, "explanation", None) or "The model declined this request.")
        text = "".join(b.text for b in message.content if b.type == "text")
        usage = message.usage.to_dict() if hasattr(message.usage, "to_dict") else {}
        return LLMResult(text=text, model=message.model, stop_reason=message.stop_reason, usage=usage)

    async def stream(self, *, system, messages, max_tokens, effort=None,
                     meta: CallMeta | None = None) -> AsyncIterator[str]:
        params, beta = self._params(system, messages, max_tokens, effort)
        api = client().beta.messages if beta else client().messages
        if not beta:
            params.pop("betas", None)
        async with api.stream(**params) as s:
            async for text in s.text_stream:
                yield text
            final = await s.get_final_message()
        if final.stop_reason == "refusal":
            raise LLMRefusal("The model declined to answer this question.")
