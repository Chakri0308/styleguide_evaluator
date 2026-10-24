import base64

from google.genai import types

from stylelens.config import get_settings
from stylelens.llm.client import get_provider, strict_schema
from stylelens.llm.gemini_provider import GeminiProvider, inline_refs, to_contents
from stylelens.extraction.rules import ExtractedRules


def test_schema_refs_are_inlined():
    schema = inline_refs(strict_schema(ExtractedRules))
    assert "$defs" not in schema and "$ref" not in str(schema)
    item = schema["properties"]["rules"]["items"]
    assert item["type"] == "object" and "statement" in item["properties"]


def test_message_conversion():
    png = base64.standard_b64encode(b"\x89PNG fake").decode()
    msgs = [
        {"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}},
                                     {"type": "text", "text": "Describe"}]},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "again"},
    ]
    out = to_contents(msgs)
    assert [c.role for c in out] == ["user", "model", "user"]
    assert out[0].parts[0].inline_data.mime_type == "image/png"
    assert out[0].parts[1].text == "Describe"
    assert isinstance(out[1], types.Content)


def test_provider_selection(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_generation_model", "gemini:gemini-flash-latest")
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    p = get_provider("generation")
    assert isinstance(p, GeminiProvider) and p.model == "gemini-flash-latest"
