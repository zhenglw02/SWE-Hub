"""Tool Stop"""

from typing import Any, Dict

from code_data_agent.model.tool import ToolInvokeResult, TOOL_INVOKER_STATUS_SUCCESS
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


class ToolStop(ToolBase):
    """Tool Stop"""

    def get_name(self) -> str:
        """Return the name of the tool."""
        return "STOP"

    def get_description(self) -> str:
        """Return the description of the tool."""
        return (
            "Call this when the task cannot be completed or no further progress can be made. "
            "Provide a concise summary explaining the failure or reason for stopping."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Return the parameters of the tool."""
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Explanation of why the task failed or must stop.",
                }
            },
            "required": ["summary"],
        }

    def invoke(self, sandbox: SandboxBase, summary: str, **kwargs) -> ToolInvokeResult:
        """Stop the agent loop"""
        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS, content=summary, need_call_llm=False
        )
