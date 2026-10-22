"""Provider-agnostic LLM interface.

Messages use the Anthropic content-block shape ({"role", "content": str | [blocks]}) as the internal
lingua franca; image blocks are {"type": "image", "source": {"type": "base64", ...}}. Other providers
translate from this shape.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMUnavailable(RuntimeError):
    """Raised when no provider is configured (e.g. missing API key)."""


class LLMRefusal(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    stop_reason: str | None = None
    usage: dict = field(default_factory=dict)


@dataclass
class CallMeta:
    """Out-of-band information about a call (used by the fake provider and for logging)."""

    prompt: str = ""
    variables: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str
    model: str

    async def complete(self, *, system: str, messages: list[dict], max_tokens: int,
                       json_schema: dict | None = None, effort: str | None = None,
                       meta: CallMeta | None = None) -> LLMResult: ...

    def stream(self, *, system: str, messages: list[dict], max_tokens: int, effort: str | None = None,
               meta: CallMeta | None = None) -> AsyncIterator[str]: ...
