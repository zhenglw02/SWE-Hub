"""Inspect a symbol."""

from typing import Any, Dict

from code_data_agent.model.tool import ToolInvokeResult, TOOL_INVOKER_STATUS_FAIL
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.sandbox.scripts import SCRIPT_NAVIGATOR
from code_data_agent.tools.tool_base import ToolBase


class ToolInspectSymbol(ToolBase):
    """Inspect a symbol."""

    def __init__(self, analyze_report_path: str = ""):
        """
        Initialize the tool.
        
        Args:
            analyze_report_path: Path to the analysis JSON file (on CFS).
                                 If provided, LLM doesn't need to pass it.
        """
        self._analyze_report_path = analyze_report_path
    def get_name(self) -> str:
        """Return the name of the tool."""
        return "INSPECT_SYMBOL"

    def get_description(self) -> str:
        """Return the description of the tool."""
        return (
            "Deep dive into a Class or Function. "
            "For Classes, it attempts to list **Member Methods**. "
            "**CRITICAL**: If the 'Member Methods' section for a Class is empty or incomplete, "
            "it indicates a limitation of static analysis. "
            "Your **FALLBACK ACTION** should be to use `read_file` on the Class's file path to manually inspect its methods."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Return the parameters of the tool."""
        # 如果已预设路径，则LLM只需要传qname
        if self._analyze_report_path:
            return {
                "type": "object",
                "properties": {
                    "qname": {
                        "type": "string",
                        "description": (
                            "The fully qualified name (e.g. 'src.utils.MyClass.run'). "
                            "Format: `{path_from_root}.{Class}.{method}`. "
                            "**Must match the file path.** If unsure, the tool will try fuzzy matching."
                        ),
                    },
                },
                "required": ["qname"],
            }
        else:
            return {
                "type": "object",
                "properties": {
                    "analyze_report_path": {
                        "type": "string",
                        "description": "Path to the repository analysis JSON file.",
                    },
                    "qname": {
                        "type": "string",
                        "description": (
                            "The fully qualified name (e.g. 'src.utils.MyClass.run'). "
                            "Format: `{path_from_root}.{Class}.{method}`. "
                            "**Must match the file path.** If unsure, the tool will try fuzzy matching."
                        ),
                    },
                },
                "required": ["analyze_report_path", "qname"],
            }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Invoke the tool with the given arguments."""
        # 优先使用预设路径，否则从参数获取
        analyze_report_path = self._analyze_report_path or kwargs.get("analyze_report_path")
        qname = kwargs.get("qname")

        missing = []
        if not analyze_report_path:
            missing.append("analyze_report_path")
        if not qname:
            missing.append("qname")
        
        if missing:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content=f"Missing required parameter(s): {', '.join(missing)}",
                need_call_llm=True,
            )

        run_args = {
            "action": "inspect_symbol",
            "analyze_report_path": analyze_report_path,
            "qname": qname,
        }

        return self._call_sandbox_script(
            sandbox, SCRIPT_NAVIGATOR, run_args, need_call_llm=True
        )
