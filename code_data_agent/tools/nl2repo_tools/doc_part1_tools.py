"""Part 1 document tools - Project level documentation.

These tools generate project-level documentation:
- Project context and introduction
- Implementation instructions
- Dependencies documentation
"""

from typing import Any, Dict

from code_data_agent.model.tool import (
    ToolInvokeResult,
    TOOL_INVOKER_STATUS_SUCCESS,
)
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


class WriteProjectContext(ToolBase):
    """Generate the 'Introduction and Objectives' section of documentation."""

    def get_name(self) -> str:
        """get_name."""
        return "WRITE_PROJECT_CONTEXT"

    def get_description(self) -> str:
        """get_description."""
        return (
            "Generate the 'Introduction and Objectives' section. "
            "Use this after analyzing the README.md and the directory structure of the target nodes. "
            "This section establishes the 'Global Context' (what the repo is) and the 'Local Context' "
            "(what the target nodes do within the repo)."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """get_parameters."""
        return {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "The name of the repository (e.g., 'ydata-profiling')."
                },
                "global_summary": {
                    "type": "string",
                    "description": "A concise summary of the entire project's purpose and key features (derived from README)."
                },
                "local_module_role": {
                    "type": "string",
                    "description": "Specific explanation of the subsystem or module where the target nodes reside. (e.g., 'The Pandas-backend statistical analysis module')."
                }
            },
            "required": ["project_name", "global_summary", "local_module_role"]
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Generate project context documentation."""
        project_name = kwargs.get("project_name", "")
        global_summary = kwargs.get("global_summary", "")
        local_module_role = kwargs.get("local_module_role", "")

        content = f"## Introduction and Objectives\n\n"
        content += f"**Project:** {project_name}\n\n"
        content += f"**Global Context:** {global_summary}\n\n"
        content += f"**Module Role (Target Scope):** {local_module_role}\n"

        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content=f"Project Context saved for {project_name}.",
            need_call_llm=True,
            extra_data={"preview": content, "section": "Project Context"}
        )


class WriteImplementInstruction(ToolBase):
    """Generate implementation instructions section."""

    def get_name(self) -> str:
        """get_name."""
        return "WRITE_IMPLEMENTATION_INSTRUCTION"

    def get_description(self) -> str:
        """get_description."""
        return (
            "Generate the 'Implementation Instructions' section. "
            "This provides step-by-step guidance on how to implement or use the target functionality, "
            "including setup requirements, configuration, and key implementation details."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """get_parameters."""
        return {
            "type": "object",
            "properties": {
                "setup_requirements": {
                    "type": "string",
                    "description": "Prerequisites and setup requirements before using the module."
                },
                "configuration_guide": {
                    "type": "string",
                    "description": "Configuration settings and options needed for the module."
                },
                "implementation_steps": {
                    "type": "string",
                    "description": "Step-by-step implementation guide for using the functionality."
                },
                "key_considerations": {
                    "type": "string",
                    "description": "Important considerations, gotchas, and best practices."
                }
            },
            "required": ["setup_requirements", "implementation_steps"]
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Generate implementation instructions."""
        setup = kwargs.get("setup_requirements", "")
        config = kwargs.get("configuration_guide", "")
        steps = kwargs.get("implementation_steps", "")
        considerations = kwargs.get("key_considerations", "")

        content = "## Implementation Instructions\n\n"
        content += f"### Setup Requirements\n{setup}\n\n"
        if config:
            content += f"### Configuration Guide\n{config}\n\n"
        content += f"### Implementation Steps\n{steps}\n\n"
        if considerations:
            content += f"### Key Considerations\n{considerations}\n"

        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content="Implementation instructions saved.",
            need_call_llm=True,
            extra_data={"preview": content, "section": "Implementation Instructions"}
        )


class WriteDependencies(ToolBase):
    """Document project dependencies."""

    def get_name(self) -> str:
        """get_name."""
        return "WRITE_DEPENDENCIES"

    def get_description(self) -> str:
        """get_description."""
        return (
            "Document the dependencies required for the target module. "
            "Include both external packages and internal module dependencies."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """get_parameters."""
        return {
            "type": "object",
            "properties": {
                "external_dependencies": {
                    "type": "string",
                    "description": "List of external packages/libraries required (e.g., 'pandas>=1.0.0, numpy')."
                },
                "internal_dependencies": {
                    "type": "string",
                    "description": "List of internal modules/classes that the target depends on."
                },
                "optional_dependencies": {
                    "type": "string",
                    "description": "Optional dependencies for extended functionality."
                }
            },
            "required": ["external_dependencies"]
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Generate dependencies documentation."""
        external = kwargs.get("external_dependencies", "")
        internal = kwargs.get("internal_dependencies", "")
        optional = kwargs.get("optional_dependencies", "")

        content = "## Dependencies\n\n"
        content += f"### External Dependencies\n{external}\n\n"
        if internal:
            content += f"### Internal Dependencies\n{internal}\n\n"
        if optional:
            content += f"### Optional Dependencies\n{optional}\n"

        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content="Dependencies documented.",
            need_call_llm=True,
            extra_data={"preview": content, "section": "Dependencies"}
        )