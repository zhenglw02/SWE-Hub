"""Tool: Bash Executor. call script: bash_func.py"""

from typing import Any, Dict

from code_data_agent.model.tool import (
    ToolInvokeResult,
    TOOL_INVOKER_STATUS_FAIL,
    TOOL_INVOKER_STATUS_SUCCESS,
)
from code_data_agent.sandbox.scripts import SCRIPT_BASH_FUNC
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


class ToolBashExecutor(ToolBase):
    def get_name(self) -> str:
        """Name of the tool. It is case-sensitive."""
        return "EXECUTE_BASH"

    def get_description(self) -> str:
        """Description of the tool. It should be concise and informative."""
        return (
            "Execute a bash command in the terminal.\n\n"
            "Behavior notes:\n"
            "• For long-running commands consider running them in the background and redirecting output.\n"
            "• If the command returns exit code -1, the process may still be running. "
            "Call this tool again to read logs or send additional input.\n"
            "• A timeout sends SIGINT; retry or take additional action if needed."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Parameters of the tool"""
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The bash command (and optional arguments) to execute. "
                        "Can be empty to fetch additional logs from a running command "
                        "or set to 'ctrl+c' to interrupt."
                    ),
                }
            },
            "required": ["command"],
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Invoke the tool with the given arguments."""

        if "command" not in kwargs:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Missing required parameter 'command'",
                need_call_llm=True,
            )

        run_args = kwargs or {}
        return self._call_sandbox_script(
            sandbox, SCRIPT_BASH_FUNC, run_args, need_call_llm=True
        )
