"""Tests for structured LLM foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from karma.llm import (
    GeminiStructuredClient,
    LLMGenerationError,
    LLMRequest,
    StructuredOutputValidationError,
    build_model_chain,
    is_transient_error,
    parse_structured_response,
)
from karma.schemas.research import ResearchBrief


@dataclass
class _FakeResponse:
    text: str


@dataclass
class _FakeModels:
    responses: list[Any] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_content(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return _FakeResponse(next_item)


@dataclass
class _FakeClient:
    models: _FakeModels


def _valid_research_json() -> str:
    return ResearchBrief(
        topic="Borrowed time",
        premise_context="A lender faces the consequences of his collections.",
    ).model_dump_json()


def test_llm_request_construction():
    request = LLMRequest(
        prompt="Research this topic.",
        system_instruction="Return valid JSON only.",
        model="gemini-2.0-flash",
        temperature=0.4,
    )

    assert request.prompt.startswith("Research")
    assert request.model == "gemini-2.0-flash"


def test_parse_structured_response_validates_model():
    parsed = parse_structured_response(_valid_research_json(), ResearchBrief)
    assert parsed.topic == "Borrowed time"


def test_parse_structured_response_rejects_invalid_json():
    with pytest.raises(StructuredOutputValidationError, match="Invalid JSON"):
        parse_structured_response("{not-json", ResearchBrief)


def test_parse_structured_response_rejects_invalid_schema():
    with pytest.raises(StructuredOutputValidationError, match="schema validation failed"):
        parse_structured_response('{"topic":"Only topic"}', ResearchBrief)


def test_is_transient_error_classification():
    assert is_transient_error(RuntimeError("503 UNAVAILABLE"))
    assert is_transient_error(RuntimeError("RESOURCE_EXHAUSTED quota"))
    assert not is_transient_error(RuntimeError("invalid API key"))


def test_build_model_chain_rotates_starting_model():
    chain = build_model_chain(
        ("gemini-2.0-flash", "gemini-2.5-flash"),
        starting_model="gemini-2.5-flash",
    )
    assert chain == ["gemini-2.5-flash", "gemini-2.0-flash"]


def test_gemini_structured_client_uses_injected_client_without_network():
    fake_client = _FakeClient(_FakeModels(responses=[_valid_research_json()]))
    client = GeminiStructuredClient(
        api_key="test-key",
        models=("gemini-2.0-flash",),
        client=fake_client,
        sleeper=lambda _seconds: None,
    )

    result = client.generate_structured(
        LLMRequest(prompt="Research topic"),
        ResearchBrief,
    )

    assert result.premise_context.startswith("A lender")
    assert fake_client.models.calls[0]["model"] == "gemini-2.0-flash"
    assert "config" in fake_client.models.calls[0]


def test_gemini_structured_client_surfaces_validation_errors():
    fake_client = _FakeClient(_FakeModels(responses=['{"topic":"Only topic"}']))
    client = GeminiStructuredClient(
        api_key="test-key",
        models=("gemini-2.0-flash",),
        client=fake_client,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(StructuredOutputValidationError):
        client.generate_structured(
            LLMRequest(prompt="Research topic"),
            ResearchBrief,
        )


def test_gemini_structured_client_retries_transient_errors_then_succeeds():
    fake_client = _FakeClient(
        _FakeModels(
            responses=[
                RuntimeError("503 UNAVAILABLE"),
                _valid_research_json(),
            ],
        ),
    )
    sleeps: list[float] = []
    client = GeminiStructuredClient(
        api_key="test-key",
        models=("gemini-2.0-flash",),
        client=fake_client,
        sleeper=sleeps.append,
    )

    result = client.generate_structured(
        LLMRequest(prompt="Research topic"),
        ResearchBrief,
    )

    assert result.topic == "Borrowed time"
    assert sleeps == [15.0]


def test_gemini_structured_client_raises_when_all_models_fail():
    fake_client = _FakeClient(
        _FakeModels(
            responses=[
                RuntimeError("503 UNAVAILABLE"),
                RuntimeError("503 UNAVAILABLE"),
                RuntimeError("503 UNAVAILABLE"),
            ],
        ),
    )
    client = GeminiStructuredClient(
        api_key="test-key",
        models=("gemini-2.0-flash",),
        max_attempts_per_model=3,
        client=fake_client,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(LLMGenerationError):
        client.generate_structured(
            LLMRequest(prompt="Research topic"),
            ResearchBrief,
        )


def test_gemini_structured_client_requires_api_key():
    with pytest.raises(ValueError, match="api_key must be provided"):
        GeminiStructuredClient(api_key="")
