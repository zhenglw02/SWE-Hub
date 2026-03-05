"""Utilities that describe LLM message payloads."""

from typing import Any, Dict

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_TOOL = "tool"
ROLE_ASSISTANT = "assistant"

class Message(object):
    """Represents a message exchanged with an LLM."""

    def __init__(
        self,
        role: str,
        content: str,
        tool_call_id: str = None,
        name: str = None,
        tool_calls: list = None,
    ):
        """Initialize the message metadata and payload content."""
        self.role = role
        self.content = content
        self.tool_call_id = tool_call_id
        self.name = name
        self.tool_calls = tool_calls or []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（便于序列化）"""
        return {
            "role": self.role,
            "content": self.content,
            "name": self.name,
            "tool_call_id": self.tool_call_id,
            "tool_calls": self.tool_calls,
        }
