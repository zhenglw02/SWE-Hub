"""model for agent"""

from typing import List

from code_data_agent.model.llm_server import Message


STOP_REASON_MAX_ITERATION = "max_iteration"
STOP_REASON_AGENT_STOP = "agent_stop"
STOP_REASON_TOOL_STOP = "tool_stop"

class AgentRunResult(object):
    """Store the result of an agent run."""
    def __init__(
        self, stop_reason: str, messages: List[Message], stop_tools: List[str] = []
    ):
        """Store the result of an agent run."""
        self.stop_reason = stop_reason
        self.stop_tools = stop_tools
        self.messages = messages

    def to_dict(self) -> dict:
        """Serialize the result into a JSON-friendly dict."""
        return {
            "stop_reason": self.stop_reason,
            "stop_tools": self.stop_tools,
            "messages": [msg.to_dict() for msg in self.messages],
        }
