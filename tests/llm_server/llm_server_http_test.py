"""Tests for the HTTP-based LLM server implementation."""

from typing import Any, Dict

import pytest

from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
from code_data_agent.model.llm_server import Message
from code_data_agent.model.tool import TOOL_INVOKER_STATUS_SUCCESS, ToolInvokeResult
from code_data_agent.tools.tool_base import ToolBase


class DummyTool(ToolBase):
    """Concrete ToolBase implementation used for testing."""

    def get_name(self) -> str:
        """Return the tool name."""
        return "dummy_tool"

    def get_description(self) -> str:
        """Describe the tool for the LLM."""
        return "Dummy tool for testing."

    def get_parameters(self) -> Dict[str, Any]:
        """Return the parameters schema."""
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    def invoke(self, sandbox, **kwargs) -> ToolInvokeResult:
        """Pretend to run the tool."""
        _ = sandbox, kwargs
        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content="ok",
            need_call_llm=False,
        )


class DummyResponse:
    """Lightweight mock of requests.Response."""

    def __init__(self, status_code: int, payload: Dict[str, Any], text: str = ""):
        """Store response attributes used by the server."""
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> Dict[str, Any]:
        """Return the provided payload."""
        return self._payload


def test_handle_message_success(monkeypatch):
    """Verify that LLMServerHTTP serializes messages and returns a Message."""
    server = LLMServerHTTP(
        base_url="http://mocked",
        model="test-model",
        model_args={"temperature": 0.1},
        headers={"Authorization": "Bearer token"},
        timeout=42,
        max_retry=0,
    )
    server.add_tools([DummyTool()])

    captured_request: Dict[str, Any] = {}

    def fake_post(url, json, headers, timeout):
        """Capture the outgoing request and return a fake response."""
        captured_request.update(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello!",
                        "tool_call_id": "tool-1",
                        "name": "assistant",
                        "tool_calls": [],
                    }
                }
            ]
        }
        return DummyResponse(status_code=200, payload=payload)

    monkeypatch.setattr("requests.post", fake_post)

    result = server.handle_message([Message(role="user", content="Hi")])

    assert captured_request["url"] == "http://mocked/chat/completions"
    assert captured_request["timeout"] == 42
    assert captured_request["headers"]["Authorization"] == "Bearer token"
    assert captured_request["json"]["model"] == "test-model"
    assert captured_request["json"]["messages"] == [
        {"role": "user", "content": "Hi"}
    ]
    assert captured_request["json"]["tools"][0]["function"]["name"] == "dummy_tool"
    assert result.role == "assistant"
    assert result.content == "Hello!"
    assert result.tool_call_id == "tool-1"


def test_handle_message_retries_and_raises(monkeypatch):
    """Ensure network errors trigger retries and surface the final exception."""
    server = LLMServerHTTP(
        base_url="http://mocked",
        model="test-model",
        max_retry=2,
    )
    attempts = {"count": 0}

    def failing_post(*_, **__):
        """Always raise to simulate network failure."""
        attempts["count"] += 1
        raise RuntimeError("network error")

    monkeypatch.setattr("requests.post", failing_post)

    with pytest.raises(RuntimeError):
        server.handle_message([Message(role="user", content="Hi")])

    assert attempts["count"] == 3
