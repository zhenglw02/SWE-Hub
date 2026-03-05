"""File editor tool."""

from typing import Any, Dict, List

from code_data_agent.model.tool import ToolInvokeResult, TOOL_INVOKER_STATUS_FAIL
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.sandbox.scripts import SCRIPT_FILE_EDITOR
from code_data_agent.tools.tool_base import ToolBase


class ToolFileEditor(ToolBase):
    """File editor tool."""

    def get_name(self) -> str:
        """Return the name of the tool."""
        return "FILE_EDITOR"

    def get_description(self) -> str:
        """Return the description of the tool."""
        return (
            "Custom editing tool for viewing, creating and editing files\n"
            "• State is persistent across command calls and discussions with the user\n"
            "• If path is a file, view displays the result of applying cat -n. "
            "If path is a directory, view lists non-hidden files and directories up to 2 levels deep\n"
            "• The create command cannot be used if the specified path already exists as a file\n"
            "• If a command generates a long output, it will be truncated and marked with <response clipped>\n"
            "• The undo_edit command will revert the last edit made to the file at path\n\n"
            "Notes for using the str_replace command:\n"
            "• The old_str parameter should match EXACTLY one or more consecutive lines from the original file. "
            "Be mindful of whitespaces!\n"
            "• If the old_str parameter is not unique in the file, the replacement will not be performed. "
            "Make sure to include enough context in old_str to make it unique\n"
            "• The new_str parameter should contain the edited lines that should replace the old_str"
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Return the parameters of the tool."""
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["view", "create", "str_replace", "insert", "undo_edit"],
                    "description": "The command to run.",
                },
                "path": {
                    "type": "string",
                    "description": "Absolute path to file or directory, e.g. /testbed/file.py or /testbed.",
                },
                "file_text": {
                    "type": "string",
                    "description": "Required for the create command. Contains the content of the file to be created.",
                },
                "old_str": {
                    "type": "string",
                    "description": "Required for the str_replace command. The exact string in path to replace.",
                },
                "new_str": {
                    "type": "string",
                    "description": (
                        "• Optional for the str_replace command to specify the replacement string.\n"
                        "• Required for the insert command to specify the string to insert."
                    ),
                },
                "insert_line": {
                    "type": "integer",
                    "description": "Required for the insert command. The new_str will be inserted after the line number specified here.",
                },
                "view_range": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "• Optional for the view command (when path is a file).\n"
                        "• If provided, specifies the line range to view, e.g. [11, 12] shows lines 11 and 12.\n"
                        "• [start_line, -1] will show all lines from start_line to the end of file."
                    ),
                },
                "concise": {
                    "type": "boolean",
                    "description": (
                        "• Optional for the view command.\n"
                        "• Defaults to True; displays a concise skeletal view of the file. "
                        "If set to False, displays the full content in the specified view_range."
                    ),
                },
            },
            "required": ["command", "path"],
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """File editor entry point."""
        missing: List[str] = [
            param for param in ("command", "path") if kwargs.get(param) is None
        ]
        if missing:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content=f"Missing required parameter(s): {', '.join(missing)}",
                need_call_llm=True,
            )

        return self._call_sandbox_script(
            sandbox, SCRIPT_FILE_EDITOR, kwargs or {}, True
        )
