"""Reset the workspace."""

from typing import Any, Dict
import shlex

from code_data_agent.model.tool import ToolInvokeResult
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


class ToolReset(ToolBase):
    """Reset the workspace."""

    def get_name(self) -> str:
        """Return the name of the tool."""
        return "RESET"

    def get_description(self) -> str:
        """Return the description of the tool."""
        return "Reset the workspace to its original clean state. \
                This command executes 'git reset --hard' and 'git clean -fd', \
                which will permanently discard all local changes, edits, and newly created files. \
                Use this to start over."

    def get_parameters(self) -> Dict[str, Any]:
        """Return the parameters of the tool."""
        return {"type": "object", "properties": {}, "required": []}

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Reset the workspace."""
        workdir = "/testbed"
        commands = [
            "git config --global --add safe.directory '/testbed' >/dev/null 2>&1 || true",
            f"cd {shlex.quote(workdir)}",
            "git restore --staged . >/dev/null 2>&1 || true",
            "git reset --hard >/dev/null 2>&1 || true",
            "git clean -fd >/dev/null 2>&1 || true",
            "git config core.autocrlf false >/dev/null 2>&1 || true",
        ]
        full_command = " && ".join(commands)
        return self._call_sandbox_command(
            sandbox, full_command, None, need_call_llm=True
        )
