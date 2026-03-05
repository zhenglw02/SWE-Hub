"""Part 2 document tools - Function/API level documentation.

These tools generate function-level documentation:
- API usage guide (signature, parameters, algorithm)
- API examples (usage demonstrations)
"""

from typing import Any, Dict

from code_data_agent.model.tool import (
    ToolInvokeResult,
    TOOL_INVOKER_STATUS_SUCCESS,
)
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


class WriteApiUsageGuide(ToolBase):
    """Record the strict 'API Contract' for a target function or class."""

    def get_name(self) -> str:
        """get_name."""
        return "WRITE_API_USAGE_GUIDE"

    def get_description(self) -> str:
        """get_description."""
        return (
            "Record the strict 'API Contract' for the target node. "
            "This information is static and compiler-oriented. "
            "Do NOT include usage examples here."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """get_parameters."""
        return {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "The exact name of the function or class."
                },
                "import_method": {
                    "type": "string",
                    "description": (
                        "The exact import statement required to use this node. "
                        "E.g., 'from ydata_profiling.model.pandas import pandas_describe_numeric_1d'. "
                        "MUST be verified from the file location."
                    )
                },
                "signature": {
                    "type": "string",
                    "description": (
                        "The full function signature including type hints. "
                        "E.g., 'def my_func(df: pd.DataFrame, config: Settings = None) -> dict:'."
                    )
                },
                "decorators": {
                    "type": "string",
                    "description": (
                        "List any decorators applied to the function "
                        "(e.g., '@multimethod', '@typechecked'). If none, return 'None'."
                    )
                },
                "parameters_desc": {
                    "type": "string",
                    "description": (
                        "Detailed description of input arguments, their types, and constraints. "
                        "Mention if an argument relies on a specific config object."
                    )
                },
                "algorithm_steps": {
                    "type": "string",
                    "description": (
                        "A concise, step-by-step explanation of the internal logic (pseudocode style). "
                        "Explain WHAT it does, not just how."
                    )
                }
            },
            "required": [
                "target_name",
                "import_method",
                "signature",
                "parameters_desc",
                "algorithm_steps"
            ]
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Generate API usage guide."""
        data = {
            "target_name": kwargs.get("target_name", ""),
            "import_method": kwargs.get("import_method", ""),
            "signature": kwargs.get("signature", ""),
            "parameters_desc": kwargs.get("parameters_desc", ""),
            "algorithm_steps": kwargs.get("algorithm_steps", ""),
            "decorators": kwargs.get("decorators", "None")
        }

        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content="API Usage Guide stored successfully.",
            need_call_llm=True,
            extra_data={"data": data, "section": "API Usage Guide"}
        )


class WriteApiExample(ToolBase):
    """Generate usage example for a target function or class."""

    def get_name(self) -> str:
        """get_name."""
        return "WRITE_API_EXAMPLE"

    def get_description(self) -> str:
        """get_description."""
        return (
            "Generate a practical usage example for the target node. "
            "This should be a runnable code snippet demonstrating how to use the API."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """get_parameters."""
        return {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "The exact name of the function or class being demonstrated."
                },
                "title": {
                    "type": "string",
                    "description": "A brief title for this example (e.g., 'Basic Usage', 'Advanced Configuration')."
                },
                "node_type": {
                    "type": "string",
                    "description": "The type of node: 'function', 'class', or 'method'."
                },
                "description": {
                    "type": "string",
                    "description": "A brief explanation of what this example demonstrates."
                },
                "code_snippet": {
                    "type": "string",
                    "description": (
                        "The actual code example. Should be complete, runnable Python code. "
                        "Include necessary imports and setup."
                    )
                }
            },
            "required": ["target_name", "title", "node_type", "description", "code_snippet"]
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Generate API example."""
        data = {
            "target_name": kwargs.get("target_name", ""),
            "title": kwargs.get("title", ""),
            "node_type": kwargs.get("node_type", ""),
            "description": kwargs.get("description", ""),
            "code_snippet": kwargs.get("code_snippet", "")
        }

        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content="API Example stored successfully.",
            need_call_llm=True,
            extra_data={"data": data, "section": "API Example"}
        )