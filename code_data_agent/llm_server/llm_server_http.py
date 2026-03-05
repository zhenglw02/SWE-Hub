"""HTTP implementation of the LLM server abstraction."""

from abc import ABCMeta
from typing import Any, Dict, List, Optional

import requests

from code_data_agent.llm_server.llm_server_base import LLMServerBase
from code_data_agent.model.llm_server import Message
from code_data_agent.tools.tool_base import ToolBase


class LLMServerHTTP(LLMServerBase, metaclass=ABCMeta):
    """Base HTTP server that serializes Message objects before sending."""

    def __init__(
        self,
        base_url: str,
        model: str,
        model_args: Dict[str, Any] = {},
        headers: Dict[str, str] = None,
        timeout: int = 600,
        max_retry: int = 0,
    ):
        """Initialize the HTTP endpoint, headers, and retry behavior."""
        self.base_url = base_url
        self.model = model
        self.model_args = model_args
        self.headers = headers or {}
        self.timeout = timeout
        self.max_retry = max_retry
        self.tool_infos = None

    def add_tools(self, tools: List[ToolBase]):
        """Build the tool descriptors expected by the HTTP API."""
        tool_infos = []
        for tool in tools:
            tool_infos.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get_name(),
                        "description": tool.get_description(),
                        "parameters": tool.get_parameters(),
                    },
                }
            )
        self.tool_infos = tool_infos

    def handle_message(self, messages: List[Message]) -> Message:
        """Serialize Message objects and send them over HTTP."""
        serialized = [self._serialize_message(m) for m in messages]
        return self._handle_serialized_messages(serialized)

    def _handle_serialized_messages(self, messages: List[Dict[str, Any]]) -> Message:
        """Perform the HTTP request with serialized payloads."""
        body = {
            "model": self.model,
            "messages": messages,
        }

        if self.tool_infos:
            body["tools"] = self.tool_infos

        if self.model_args:
            body.update(self.model_args)

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retry + 1):
            try:
                response = requests.post(
                    self.base_url + "/chat/completions",
                    json=body,
                    headers=self.headers,
                    timeout=self.timeout,
                )

                if response.status_code != 200:
                    raise Exception(
                        f"[LLMServerHTTP]: response status_code not 200, is: {response.status_code}, \
                        response body: {response.text}"
                    )

                payload = response.json()
                choice = (payload.get("choices") or [{}])[0]
                message_data = choice.get("message", {})

                return Message(
                    role=message_data.get("role"),
                    content=message_data.get("content"),
                    tool_call_id=message_data.get("tool_call_id"),
                    name=message_data.get("name"),
                    tool_calls=message_data.get("tool_calls"),
                )
            except Exception as exc:
                last_error = exc
                if attempt == self.max_retry:
                    raise exc

        raise last_error or Exception("[LLMServerHTTP]: Unknown error during request.")

    def _serialize_message(self, message: Message) -> Dict[str, Any]:
        """Convert a Message model into the dict structure used by HTTP."""
        data: Dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_call_id:
            data["tool_call_id"] = message.tool_call_id
        if message.name:
            data["name"] = message.name
        if message.tool_calls:
            data["tool_calls"] = message.tool_calls
        return data
