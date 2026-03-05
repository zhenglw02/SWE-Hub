"""Abstract base definitions for LLM server implementations."""

from abc import ABCMeta, abstractmethod
from typing import List

from code_data_agent.model.llm_server import Message
from code_data_agent.tools.tool_base import ToolBase


class LLMServerBase(metaclass=ABCMeta):
    """Contract for servers that wrap different LLM providers."""

    @abstractmethod
    def add_tools(self, tools: List[ToolBase]):
        """Register a list of tools that the LLM may call."""

    @abstractmethod
    def handle_message(self, messages: List[Message]) -> Message:
        """Send a conversation history to the LLM and return its response."""
