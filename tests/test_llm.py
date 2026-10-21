"""LLM client: AnthropicClient against a fake SDK, FakeLLMClient, config. No network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from grader.llm import (
    MODEL_PLACEHOLDER,
    AnthropicClient,
    FakeLLMClient,
    LLMError,
    LLMRequest,
    load_llm_config,
)

TOOL = {
    "name": "submit_x",
    "description": "Submit x.",
    "input_schema": {"type": "object", "properties": {"x": {"type": "integer"}}},
}


class FakeSDK:
    """Stands in for ``anthropic.Anthropic``: records constructor and create() kwargs."""

    def __init__(self, reply: dict | Exception):
        self.reply, self.init_kwargs, self.calls = reply, None, []
        self.messages = SimpleNamespace(create=self._create)

    def factory(self, **kwargs):
        self.init_kwargs = kwargs
        return self

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(to_dict=lambda: self.reply)


def _reply(content: list[dict]) -> dict:
    return {
        "model": "m-1",
        "stop_reason": "tool_use",
        "content": content,
        "usage": {"input_tokens": 12, "output_tokens": 7},
    }


def _req(**kw) -> LLMRequest:
    base = dict(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool=TOOL,
        model="m-1",
        max_tokens=99,
    )
    return LLMRequest(**{**base, **kw})


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


def test_forced_tool_choice_and_schema(key) -> None:
    sdk = FakeSDK(_reply([{"type": "tool_use", "id": "t1", "name": "submit_x", "input": {"x": 1}}]))
    client = AnthropicClient(timeout_s=5, max_retries=3, sdk_factory=sdk.factory)
    resp = client.complete(_req())
    assert sdk.init_kwargs == {"api_key": "sk-test", "timeout": 5, "max_retries": 3}
    (call,) = sdk.calls
    assert call["tool_choice"] == {"type": "tool", "name": "submit_x"}
    assert call["tools"] == [TOOL]
    assert call["system"] == "sys" and call["max_tokens"] == 99 and call["model"] == "m-1"
    assert "temperature" not in call  # rejected by the API since 2026-10-21 (D36)
    assert resp.tool_input == {"x": 1}
    assert (resp.input_tokens, resp.output_tokens, resp.model) == (12, 7, "m-1")


def test_auto_tool_choice_when_not_forced(key) -> None:
    sdk = FakeSDK(_reply([{"type": "tool_use", "id": "t1", "name": "submit_x", "input": {}}]))
    AnthropicClient(force_tool=False, sdk_factory=sdk.factory).complete(_req())
    assert sdk.calls[0]["tool_choice"] == {"type": "auto"}


def test_temperature_is_refused_before_any_call(key) -> None:
    sdk = FakeSDK(_reply([]))
    with pytest.raises(LLMError, match="temperature"):
        AnthropicClient(sdk_factory=sdk.factory).complete(_req(temperature=0.0))
    assert sdk.calls == []


def test_missing_key_raises_only_on_complete(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sdk = FakeSDK(_reply([]))
    client = AnthropicClient(sdk_factory=sdk.factory)  # constructing is fine without a key
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        client.complete(_req())
    assert sdk.init_kwargs is None and sdk.calls == []


def test_no_tool_call_is_an_llm_error(key) -> None:
    sdk = FakeSDK(_reply([{"type": "text", "text": "I'd rather not."}]))
    with pytest.raises(LLMError, match="no 'submit_x' tool call"):
        AnthropicClient(sdk_factory=sdk.factory).complete(_req())


def test_sdk_exception_becomes_llm_error(key) -> None:
    sdk = FakeSDK(RuntimeError("503 overloaded"))
    with pytest.raises(LLMError, match="503 overloaded"):
        AnthropicClient(sdk_factory=sdk.factory).complete(_req())


def test_fake_client_scripts_and_records() -> None:
    fake = FakeLLMClient([FakeLLMClient.tool_call("submit_x", {"x": 2}), LLMError("boom")])
    assert fake.complete(_req()).tool_input == {"x": 2}
    with pytest.raises(LLMError, match="boom"):
        fake.complete(_req())
    with pytest.raises(LLMError, match="no scripted responses"):
        fake.complete(_req())
    assert len(fake.requests) == 3


def test_committed_config_is_a_placeholder(root) -> None:
    cfg = load_llm_config(root / "config" / "llm.yaml")
    assert cfg.model == MODEL_PLACEHOLDER and cfg.temperature is None
    with pytest.raises(LLMError, match="placeholder"):
        cfg.check()
