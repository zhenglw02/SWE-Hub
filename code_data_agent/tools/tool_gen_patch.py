"""Generate a patch of staged modifications since HEAD."""

from typing import Any, Dict, List

from code_data_agent.model.tool import (
    ToolInvokeResult,
    TOOL_INVOKER_STATUS_FAIL,
    TOOL_INVOKER_STATUS_SUCCESS,
)
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


TARGET_EXTENSIONS: List[str] = [
    "*.py",
    "*.java",
    "*.js",
    "*.ts",
    "*.cpp",
    "*.c",
    "*.h",
    "*.hpp",
    "*.go",
    "*.rs",
    "*.php",
    "*.rb",
]

extensions_str = " ".join([f"'{ext}'" for ext in TARGET_EXTENSIONS])


class ToolGenPatch(ToolBase):
    """Generate a patch of staged modifications since HEAD."""

    def get_name(self) -> str:
        """Tool name."""
        return "GEN_PATCH"

    def get_description(self) -> str:
        """Tool description."""
        return (
            "Generate a unified diff (patch) of staged modifications since HEAD. "
            "Only source files with common extensions are included."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Tool parameters."""
        return {"type": "object", "properties": {}, "required": []}

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Tool invocation."""
        add_result = sandbox.run_command("cd /testbed && git add --all", None)
        if add_result.exit_code != 0:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Failed to stage changes before diffing.",
                need_call_llm=False,
            )

        baseline_cmd = "cat .agent_baseline_sha 2>/dev/null || echo HEAD"
        baseline_sha_result = sandbox.run_command(baseline_cmd, None)
        if baseline_sha_result.exit_code != 0:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Failed to retrieve baseline commit SHA.",
                need_call_llm=False,
            )

        baseline_sha = baseline_sha_result.output.strip()
        diff_cmd = f"cd /testbed && git diff {baseline_sha} --cached --binary --no-color -- {extensions_str}"
        diff_result = sandbox.run_command(diff_cmd, None)
        if diff_result.exit_code != 0:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Failed to generate git diff.",
                need_call_llm=False,
            )

        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content=diff_result.output.strip(),
            need_call_llm=True,
        )
