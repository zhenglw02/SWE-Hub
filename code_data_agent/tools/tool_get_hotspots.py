"""Get hotspots from a repository."""

from typing import Any, Dict

from code_data_agent.model.tool import (
    ToolInvokeResult,
    TOOL_INVOKER_STATUS_FAIL,
)
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.sandbox.scripts import SCRIPT_NAVIGATOR
from code_data_agent.tools.tool_base import ToolBase


class ToolGetHotspots(ToolBase):
    """Get hotspots from a repository."""

    def __init__(self, analyze_report_path: str = ""):
        """
        Initialize the tool.
        
        Args:
            analyze_report_path: Path to the analysis JSON file (on CFS).
                                 If provided, LLM doesn't need to pass it.
        """
        self._analyze_report_path = analyze_report_path

    def get_name(self) -> str:
        """Get the name of the tool."""
        return "GET_HOTSPOTS"

    def get_description(self) -> str:
        """Get the description of the tool."""
        return (
            "Scout for targets. Returns a randomized sample from the repository. "
            "For Classes, it may list **Available Methods** based on static analysis. "
            "**NOTE**: This method list can be INCOMPLETE. If a Class looks promising but has few listed methods, "
            "it is highly recommended to `inspect_symbol` on the Class itself to get a better view."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Get the parameters of the tool."""
        # 如果已预设路径，则LLM不需要传参
        if self._analyze_report_path:
            return {
                "type": "object",
                "properties": {
                    "start_index": {
                        "type": "integer",
                        "default": 0,
                        "description": "Start rank (0-based). Default is 0.",
                    },
                    "end_index": {
                        "type": "integer",
                        "default": 10,
                        "description": "End rank (exclusive). Returns 10 items by default.",
                    },
                },
                "required": [],
            }
        else:
            return {
                "type": "object",
                "properties": {
                    "analyze_report_path": {
                        "type": "string",
                        "description": "Path to the repository analysis JSON file.",
                    },
                    "start_index": {
                        "type": "integer",
                        "default": 0,
                        "description": "Start rank (0-based). Default is 0.",
                    },
                    "end_index": {
                        "type": "integer",
                        "default": 10,
                        "description": "End rank (exclusive). Returns 10 items by default.",
                    },
                },
                "required": ["analyze_report_path"],
            }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Invoke the tool with the given sandbox and keyword arguments."""
        # 优先使用预设路径，否则从参数获取
        analyze_report_path = self._analyze_report_path or kwargs.get("analyze_report_path")
        
        if not analyze_report_path:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Missing required parameter 'analyze_report_path'",
                need_call_llm=True,
            )

        start_index = kwargs.get("start_index", 0)
        end_index = kwargs.get("end_index", 10)
        run_args = {
            "action": "get_hotspots",
            "analyze_report_path": analyze_report_path,
            "start_index": start_index,
            "end_index": end_index,
        }

        return self._call_sandbox_script(
            sandbox, SCRIPT_NAVIGATOR, run_args, need_call_llm=True
        )
