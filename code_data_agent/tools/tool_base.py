"""Abstract interface all callable tools must implement."""

from typing import Any, Dict
from abc import ABCMeta, abstractmethod

from code_data_agent.model.tool import ToolInvokeResult, TOOL_INVOKER_STATUS_SUCCESS, TOOL_INVOKER_STATUS_FAIL
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.model.sandbox import SandboxScript

class ToolBase(metaclass=ABCMeta):
    """Base class for tools that can be invoked by the agent."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the unique identifier for the tool."""

    @abstractmethod
    def get_description(self) -> str:
        """Describe the tool so the LLM can decide when to use it."""

    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Return a JSON schema that documents required parameters."""

    @abstractmethod
    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Execute the tool inside the sandbox using the provided arguments."""

    def _call_sandbox_script(self, sandbox: SandboxBase, script: SandboxScript, run_args: dict, need_call_llm: bool) -> ToolInvokeResult:
        """Helper method to invoke a sandbox script."""
        run_result = sandbox.run_script(script, run_args)
        status = (
            TOOL_INVOKER_STATUS_SUCCESS
            if run_result.exit_code == 0
            else TOOL_INVOKER_STATUS_FAIL
        )
        output = run_result.output or ""
        formatted = f"[exit_code={run_result.exit_code}]\n{output}".strip()
        return ToolInvokeResult(
            status=status, content=formatted, need_call_llm=need_call_llm
        )

    def _call_sandbox_command(
        self,
        sandbox: SandboxBase,
        command: str,
        run_args: dict,
        need_call_llm: bool,
    ) -> ToolInvokeResult:
        """Helper method to invoke a sandbox command."""
        run_result = sandbox.run_command(command=command, args=run_args)
        status = (
            TOOL_INVOKER_STATUS_SUCCESS
            if run_result.exit_code == 0
            else TOOL_INVOKER_STATUS_FAIL
        )
        output = run_result.output or ""
        formatted = f"[exit_code={run_result.exit_code}]\n{output}".strip()
        return ToolInvokeResult(
            status=status, content=formatted, need_call_llm=need_call_llm
        )
