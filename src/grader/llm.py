"""Minimal LLM client: one interface, an Anthropic implementation and a scripted fake.

Nothing here may influence a verdict. Callers turn every failure into ``LLMError``.
"""

from __future__ import annotations

import copy
import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

import yaml

API_KEY_ENV = "ANTHROPIC_API_KEY"
MODEL_PLACEHOLDER = "SET-A-CURRENT-CLAUDE-MODEL-ID"


class LLMError(Exception):
    """The LLM call failed: no key, API error, or no tool call in the response."""


class NoToolCallError(LLMError):
    """The call worked, but the model answered without calling the tool (e.g. plain text
    under ``tool_choice: auto``). ``response`` lets a caller retry in the same thread."""

    def __init__(self, message: str, response: LLMResponse):
        super().__init__(message)
        self.response = response


@dataclass
class LLMRequest:
    system: str
    messages: list[dict]  # Anthropic message format
    tool: dict | None  # one tool definition: {name, description, input_schema}
    model: str
    max_tokens: int
    temperature: float | None = None  # None = not sent (see decisions.md D36)


@dataclass
class LLMResponse:
    tool_input: dict | None  # the tool call's arguments
    raw: dict  # full response, saved for reproducibility
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float


class LLMClient(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...


# ------------------------------------------------------------------------------- config


@dataclass(frozen=True)
class LLMConfig:
    model: str = MODEL_PLACEHOLDER
    plan_max_tokens: int = 16000
    feedback_max_tokens: int = 4000
    temperature: float | None = None
    timeout_s: float = 120.0
    max_retries: int = 2
    force_tool: bool = False  # current models reject forced tool_choice (D37)

    def check(self) -> None:
        if not self.model or self.model == MODEL_PLACEHOLDER:
            raise LLMError(
                "config/llm.yaml: 'model' is still the placeholder; set a current Claude "
                "model ID from Anthropic's docs."
            )


def load_llm_config(path: str | Path) -> LLMConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    mt = data.get("max_tokens") or {}
    return LLMConfig(
        model=str(data.get("model") or MODEL_PLACEHOLDER),
        plan_max_tokens=int(mt.get("plan", 16000)),
        feedback_max_tokens=int(mt.get("feedback", 4000)),
        temperature=data.get("temperature"),
        timeout_s=float(data.get("timeout_s", 120.0)),
        max_retries=int(data.get("max_retries", 2)),
        force_tool=bool(data.get("force_tool", False)),
    )


def require_api_key() -> str:
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise LLMError(f"{API_KEY_ENV} is not set; export your Anthropic API key first.")
    return key


# ------------------------------------------------------------------------------ prompts


def load_prompt(name: str) -> tuple[str, str]:
    """Return (text, version); the version is the first 8 hex chars of the file's SHA-256
    (CRLF normalised to LF, so a Windows checkout gives the same version)."""
    data = resources.files("grader.prompts").joinpath(name).read_bytes().replace(b"\r\n", b"\n")
    return data.decode("utf-8"), hashlib.sha256(data).hexdigest()[:8]


# ------------------------------------------------------------------------------ clients


def tool_use_block(raw: dict, name: str | None = None) -> dict | None:
    """The first ``tool_use`` content block (optionally with the given name)."""
    for block in raw.get("content") or []:
        if block.get("type") == "tool_use" and (name is None or block.get("name") == name):
            return block
    return None


class AnthropicClient:
    """Calls the Messages API through the official SDK (``pip install -e .[llm]``).

    ``sdk_factory`` builds the SDK client from keyword arguments; tests inject a fake.
    """

    def __init__(
        self,
        *,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        force_tool: bool = False,
        sdk_factory: Callable[..., Any] | None = None,
    ):
        self.timeout_s, self.max_retries, self.force_tool = timeout_s, max_retries, force_tool
        self._factory = sdk_factory
        self._sdk: Any = None

    @classmethod
    def from_config(cls, cfg: LLMConfig) -> AnthropicClient:
        return cls(timeout_s=cfg.timeout_s, max_retries=cfg.max_retries, force_tool=cfg.force_tool)

    def _client(self) -> Any:
        key = require_api_key()  # read only now, never at import or construction
        if self._sdk is None:
            factory = self._factory
            if factory is None:
                try:
                    import anthropic
                except ImportError:
                    raise LLMError(
                        "the anthropic SDK is not installed; run: pip install -e .[llm]"
                    ) from None
                factory = anthropic.Anthropic
            self._sdk = factory(api_key=key, timeout=self.timeout_s, max_retries=self.max_retries)
        return self._sdk

    def complete(self, req: LLMRequest) -> LLMResponse:
        if req.temperature is not None:
            raise LLMError(
                "temperature is no longer accepted by the Messages API; set "
                "'temperature: null' in config/llm.yaml."
            )
        sdk = self._client()
        kwargs: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "system": req.system,
            "messages": req.messages,
        }
        if req.tool is not None:
            kwargs["tools"] = [req.tool]
            kwargs["tool_choice"] = (
                {"type": "tool", "name": req.tool["name"]} if self.force_tool else {"type": "auto"}
            )
        t0 = time.monotonic()
        try:
            resp = sdk.messages.create(**kwargs)
        except Exception as exc:  # any SDK/network failure only means "no LLM output"
            raise LLMError(f"Anthropic API call failed: {type(exc).__name__}: {exc}") from None
        latency = time.monotonic() - t0
        raw = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
        usage = raw.get("usage") or {}
        out = LLMResponse(
            tool_input=None,
            raw=raw,
            model=str(raw.get("model", req.model)),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            latency_s=round(latency, 3),
        )
        return check_tool_call(req, out)


def check_tool_call(req: LLMRequest, resp: LLMResponse) -> LLMResponse:
    """Fill ``tool_input`` from the response, or raise ``NoToolCallError``."""
    if req.tool is None:
        return resp
    block = tool_use_block(resp.raw, req.tool["name"])
    if block is None:
        raise NoToolCallError(
            f"the response has no '{req.tool['name']}' tool call "
            f"(stop_reason={resp.raw.get('stop_reason')!r})",
            resp,
        )
    resp.tool_input = block.get("input")
    return resp


@dataclass
class FakeLLMClient:
    """Returns scripted responses in order (an Exception is raised instead) and records
    every request it receives."""

    responses: list[LLMResponse | Exception]
    requests: list[LLMRequest] = field(default_factory=list)

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(copy.deepcopy(req))
        if not self.responses:
            raise LLMError("FakeLLMClient: no scripted responses left")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return check_tool_call(req, nxt)  # same rule as AnthropicClient

    @staticmethod
    def tool_call(name: str, tool_input: dict, n: int = 1) -> LLMResponse:
        """A scripted response containing one tool call with id ``toolu_<n>``."""
        block = {"type": "tool_use", "id": f"toolu_{n}", "name": name, "input": tool_input}
        return FakeLLMClient._response([block], "tool_use", tool_input, n)

    @staticmethod
    def text_reply(text: str, n: int = 1) -> LLMResponse:
        """A scripted plain-text answer with no tool call."""
        return FakeLLMClient._response([{"type": "text", "text": text}], "end_turn", None, n)

    @staticmethod
    def _response(content: list[dict], stop: str, tool_input: dict | None, n: int) -> LLMResponse:
        raw = {
            "id": f"msg_{n}",
            "type": "message",
            "role": "assistant",
            "model": "fake-model",
            "stop_reason": stop,
            "content": content,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        return LLMResponse(tool_input, raw, "fake-model", 100, 50, 0.0)
