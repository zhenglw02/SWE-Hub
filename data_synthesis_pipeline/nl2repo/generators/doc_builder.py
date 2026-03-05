"""Document builder for generating comprehensive project documentation.

Assembles documentation from various sources including project context,
API documentation, and usage examples.
"""

from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from nl2repo.models.entity import CodeEntity
    from nl2repo.models.task import MetaInfo


def build_full_doc(
    part_1_doc: Dict[str, str],
    entity_pair_list: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    meta: "MetaInfo",
) -> str:
    """Build complete documentation from components.
    
    Args:
        part_1_doc: Project-level documentation with keys:
            - WRITE_PROJECT_CONTEXT
            - WRITE_IMPLEMENTATION_INSTRUCTION
            - WRITE_DEPENDENCIES
        entity_pair_list: List of (entity_dict, doc_dict) tuples
        meta: Repository metadata including workdir_tree
        
    Returns:
        Complete documentation string
    """
    # Build main sections
    prompt_list = [
        part_1_doc.get("WRITE_PROJECT_CONTEXT", ""),
        part_1_doc.get("WRITE_IMPLEMENTATION_INSTRUCTION", ""),
        part_1_doc.get("WRITE_DEPENDENCIES", ""),
        f"Recommended Project Tree Structure\n{meta.workdir_tree or ''}",
        "",
    ]
    
    # Build API documentation section
    api_implement_list = [
        "## API Interface Documentation",
    ]
    
    # Build examples section
    api_example_list = [
        "## Functional Nodes and Test Interface Examples",
    ]
    
    local_repo_path = meta.local_repo_path or ""
    
    for entity, pair_dict in entity_pair_list:
        # Build workdir path
        workdir_path = "{}::{}".format(
            entity.get("file_path", ""),
            entity.get("qname", entity.get("name", "")),
        ).replace(local_repo_path, "/testbed")
        
        # API Usage Guide
        usage_guide = pair_dict.get("WRITE_API_USAGE_GUIDE", {})
        api_implement_list.append(f"### {workdir_path}")
        api_implement_list.append(
            f"**Import Method**: `{usage_guide.get('import_method', '')}`"
        )
        api_implement_list.append(
            f"**Decorator**: `{usage_guide.get('decorators', '')}`"
        )
        api_implement_list.append(
            f"**Signature**: \n```python\n{usage_guide.get('signature', '')}\n```"
        )
        api_implement_list.append(
            f"**Parameters**: \n`{usage_guide.get('parameters_desc', '')}`"
        )
        api_implement_list.append(
            f"**Docstring**: \n`{usage_guide.get('algorithm_steps', '')}`"
        )
        api_implement_list.append("\n")
        
        # API Example
        api_example = pair_dict.get("WRITE_API_EXAMPLE", {})
        api_example_list.append(f"### {workdir_path}")
        api_example_list.append(f"**Title**: `{api_example.get('title', '')}`")
        api_example_list.append(f"**Type**: `{api_example.get('node_type', '')}`")
        api_example_list.append(
            f"**Function Description**: \n`{api_example.get('description', '')}`"
        )
        api_example_list.append(
            f"**Example**: \n```python\n{api_example.get('code_snippet', '')}\n```"
        )
    
    return "\n".join(prompt_list + api_implement_list + api_example_list)


class DocBuilder:
    """High-level document builder with configurable templates."""
    
    def __init__(
        self,
        template_project_context: Optional[str] = None,
        template_api_section: Optional[str] = None,
        template_example_section: Optional[str] = None,
    ):
        """Initialize document builder.
        
        Args:
            template_project_context: Template for project context section
            template_api_section: Template for API documentation
            template_example_section: Template for examples section
        """
        self.template_project_context = template_project_context
        self.template_api_section = template_api_section
        self.template_example_section = template_example_section
    
    def build(
        self,
        part_1_doc: Dict[str, str],
        entity_pair_list: List[Tuple[Dict[str, Any], Dict[str, Any]]],
        meta: "MetaInfo",
    ) -> str:
        """Build documentation.
        
        Args:
            part_1_doc: Project-level documentation
            entity_pair_list: Entity and documentation pairs
            meta: Repository metadata
            
        Returns:
            Complete documentation string
        """
        return build_full_doc(part_1_doc, entity_pair_list, meta)
    
    def build_minimal(
        self,
        project_name: str,
        description: str,
        tree_structure: str,
        entities: List[Dict[str, Any]],
    ) -> str:
        """Build minimal documentation without external doc sources.
        
        Args:
            project_name: Name of the project
            description: Project description
            tree_structure: Directory tree string
            entities: List of entity dictionaries
            
        Returns:
            Minimal documentation string
        """
        lines = [
            f"# {project_name}",
            "",
            description,
            "",
            "## Project Structure",
            "```",
            tree_structure,
            "```",
            "",
            "## Code Entities",
            "",
        ]
        
        for entity in entities:
            lines.append(f"### {entity.get('qname', entity.get('name', 'Unknown'))}")
            lines.append(f"- **File**: `{entity.get('file_path', '')}`")
            lines.append(f"- **Lines**: {entity.get('line_start', 0)}-{entity.get('line_end', 0)}")
            lines.append(f"- **Type**: {entity.get('code_type', '')}")
            
            if entity.get("signature"):
                lines.append(f"- **Signature**: `{entity['signature']}`")
            
            lines.append("")
        
        return "\n".join(lines)