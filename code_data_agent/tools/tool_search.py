"""Search tool."""

from typing import Any, Dict

from code_data_agent.model.tool import ToolInvokeResult, TOOL_INVOKER_STATUS_FAIL
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.sandbox.scripts import SCRIPT_SEARCH_FUNC
from code_data_agent.tools.tool_base import ToolBase


class ToolSearch(ToolBase):
    """Search tool."""

    def get_name(self) -> str:
        """Return the name of the tool."""
        return "SEARCH"

    def get_description(self) -> str:
        """Return the description of the tool."""
        return (
            "Search for a term in a directory or a single file.\n"
            "• If path is a directory (or unspecified, default is .), it recursively searches all non-hidden files "
            "and directories for the search term.\n"
            "• If path points to a file, it runs a grep -n in that file to show line numbers matching the search term.\n"
            "• If more than 100 files match in a directory search, results are truncated and the tool will inform you "
            "to narrow your search.\n"
            "• If no matches are found, it will inform you as well."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Return the parameters of the tool."""
        return {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "The term or string to search for in files.",
                },
                "path": {
                    "type": "string",
                    "description": "The file or directory to search in. Defaults to . if not specified.",
                },
            },
            "required": ["search_term"],
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """invoke."""
        search_term = kwargs.get("search_term")
        if not search_term:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Missing required parameter 'search_term'",
                need_call_llm=True,
            )

        return self._call_sandbox_script(sandbox, SCRIPT_SEARCH_FUNC, kwargs or {}, True)
