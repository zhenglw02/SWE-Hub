"""Document generation agents for nl2repo.

These agents generate documentation for code repositories:
- DocPart1Agent: Project-level documentation (context, instructions, dependencies)
- DocPart2Agent: Function/API-level documentation (usage guide, examples)

Usage pattern follows k8s_bug_agent.py - just assemble tools, prompt, and run.
"""

import json
from typing import Any, Dict, List, Optional

from code_data_agent.agent.agent import Agent
from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_bash_executor import ToolBashExecutor
from code_data_agent.tools.tool_search import ToolSearch
from code_data_agent.tools.tool_stop import ToolStop

from nl2repo.agents.prompts import DOC_PART1_PROMPT, DOC_PART2_PROMPT
from code_data_agent.tools.nl2repo_tools.doc_part1_tools import (
    WriteProjectContext,
    WriteImplementInstruction,
    WriteDependencies,
)
from code_data_agent.tools.nl2repo_tools.doc_part2_tools import (
    WriteApiUsageGuide,
    WriteApiExample,
)
from code_data_agent.tools.nl2repo_tools.tool_static_call_graph import (
    SimplePythonCallGraph,
    ToolStaticCallGraph,
)


def create_doc_part1_tools() -> list:
    """Create tool list for Part 1 (project-level) documentation agent."""
    return [
        # Exploration tools
        ToolBashExecutor(),
        ToolSearch(),
        # Documentation tools
        WriteProjectContext(),
        WriteImplementInstruction(),
        WriteDependencies(),
        # Control tools
        ToolStop(),
    ]


def create_doc_part2_tools(
    grapher: Optional[SimplePythonCallGraph] = None,
    local_workdir: str = "",
    kodo_workdir: str = "/testbed",
) -> list:
    """Create tool list for Part 2 (function-level) documentation agent.
    
    Args:
        grapher: Pre-built SimplePythonCallGraph instance (optional)
        local_workdir: Local repository path
        kodo_workdir: Container repository path
    """
    tools = [
        # Exploration tools
        ToolBashExecutor(),
        ToolSearch(),
    ]
    
    # Add static call graph tool if grapher is provided
    if grapher is not None:
        tools.append(ToolStaticCallGraph(grapher, local_workdir, kodo_workdir))
    
    # Documentation tools
    tools.extend([
        WriteApiUsageGuide(),
        WriteApiExample(),
        # Control tools
        ToolStop(),
    ])
    
    return tools


def run_doc_agent(
    agent: Agent,
    context_prompt: str,
) -> Dict[str, Any]:
    """Run a documentation agent and extract results.
    
    Args:
        agent: Configured Agent instance
        context_prompt: Context information as user prompt
        
    Returns:
        Dictionary containing status, messages, and collected results
    """
    result = agent.run(prompt=context_prompt)
    
    # Extract collected data from tool results
    collected = {}
    for message in result.messages:
        if message.role == "tool" and message.content:
            try:
                tool_result = json.loads(message.content)
                extra_data = tool_result.get("extra_data", {})
                if extra_data:
                    if "preview" in extra_data:
                        section = extra_data.get("section", "unknown")
                        collected[section] = extra_data["preview"]
                    if "data" in extra_data:
                        section = extra_data.get("section", "unknown")
                        collected[section] = extra_data["data"]
            except (json.JSONDecodeError, TypeError):
                pass
    
    # Determine status
    status = result.stop_reason
    if result.stop_tools and "STOP" in result.stop_tools:
        status = "STOP"
    
    return {
        "status": status,
        "stop_tools": result.stop_tools,
        "messages": [m.to_dict() for m in result.messages],
        "result_dict": collected,
    }


def build_part1_context(
    instance: Dict[str, Any],
    workdir_tree: str,
    local_workdir: str,
    kodo_workdir: str,
) -> str:
    """Build context prompt for Part 1 agent.
    
    Args:
        instance: Cluster instance with entities
        workdir_tree: Project directory tree
        local_workdir: Local repository path
        kodo_workdir: Container repository path
        
    Returns:
        Context prompt string
    """
    node_names = []
    for entity in instance.get('entities', []):
        origin_name = f"{entity['file_path']}::{entity['qname']}"
        node_name = origin_name.replace(local_workdir, kodo_workdir)
        node_names.append(node_name)
    node_names.sort()
    
    return "\n".join([
        "## Cluster Nodes:",
        "\n".join(node_names),
        "",
        "## Project Tree Structure:",
        workdir_tree,
    ])


def build_part2_context(
    entity: Dict[str, Any],
    dynamic_map: Optional[Dict[str, Any]] = None,
    local_workdir: str = "",
    kodo_workdir: str = "/testbed",
) -> str:
    """Build context prompt for Part 2 agent.
    
    Args:
        entity: Entity dictionary with code information
        dynamic_map: Optional dynamic coverage/call graph data
        local_workdir: Local repository path
        kodo_workdir: Container repository path
        
    Returns:
        Context prompt string
    """
    target_path = f"{entity['file_path']}::{entity['qname']}".replace(
        local_workdir, kodo_workdir
    )
    
    context_parts = [
        f"## Target: {target_path}",
        f"## Type: {entity.get('code_type', 'function')}",
        f"## Lines: {entity.get('line_start', 0)}-{entity.get('line_end', 0)}",
    ]
    
    if entity.get('signature'):
        context_parts.append(f"## Signature: {entity['signature']}")
    
    if entity.get('src_code'):
        context_parts.append(f"\n## Source Code:\n```python\n{entity['src_code']}\n```")
    
    if dynamic_map:
        key = f"{entity['file_path']}::{entity['qname']}"
        if key in dynamic_map.get('function_to_tests', {}):
            tests = dynamic_map['function_to_tests'][key][:5]
            context_parts.append(f"\n## Related Tests:\n" + "\n".join(f"- {t}" for t in tests))
    
    return "\n".join(context_parts)


# ============================================================================
# High-level convenience classes (optional, for backward compatibility)
# ============================================================================

class DocPart1Agent:
    """Wrapper for Part 1 (project-level) documentation agent.
    
    Example usage:
        llm_server = LLMServerHTTP(
            base_url="https://api.example.com/v2",
            model="your-model-name",
            headers={"Authorization": "Bearer xxx"},
        )
        
        agent = DocPart1Agent(llm_server=llm_server, sandbox=sandbox)
        result = agent.generate_docs(instance, workdir_tree, local_workdir, kodo_workdir)
    """
    
    def __init__(
        self,
        llm_server: LLMServerHTTP,
        sandbox: SandboxBase,
        system_prompt: Optional[str] = None,
        max_iterations: int = 100,
    ):
        """__init__."""
        self.tools = create_doc_part1_tools()
        self.agent = Agent(
            system_prompt=system_prompt or DOC_PART1_PROMPT,
            tools=self.tools,
            llm_server=llm_server,
            sandbox=sandbox,
            max_iterations=max_iterations,
        )
    
    def generate_docs(
        self,
        instance: Dict[str, Any],
        workdir_tree: str,
        local_workdir: str,
        kodo_workdir: str,
    ) -> Dict[str, Any]:
        """Generate Part 1 documentation for a cluster instance."""
        context = build_part1_context(instance, workdir_tree, local_workdir, kodo_workdir)
        return run_doc_agent(self.agent, context)


class DocPart2Agent:
    """Wrapper for Part 2 (function-level) documentation agent.
    
    Example usage:
        llm_server = LLMServerHTTP(
            base_url="https://api.example.com/v2",
            model="your-model-name",
            headers={"Authorization": "Bearer xxx"},
        )
        
        grapher = SimplePythonCallGraph(repo_path)
        agent = DocPart2Agent(
            llm_server=llm_server,
            sandbox=sandbox,
            grapher=grapher,
            local_workdir=local_workdir,
            kodo_workdir="/testbed",
        )
        result = agent.generate_docs(entity, dynamic_map)
    """
    
    def __init__(
        self,
        llm_server: LLMServerHTTP,
        sandbox: SandboxBase,
        system_prompt: Optional[str] = None,
        max_iterations: int = 100,
        grapher: Optional[SimplePythonCallGraph] = None,
        local_workdir: str = "",
        kodo_workdir: str = "/testbed",
    ):
        """__init__."""
        self.local_workdir = local_workdir
        self.kodo_workdir = kodo_workdir
        self.tools = create_doc_part2_tools(grapher, local_workdir, kodo_workdir)
        self.agent = Agent(
            system_prompt=system_prompt or DOC_PART2_PROMPT,
            tools=self.tools,
            llm_server=llm_server,
            sandbox=sandbox,
            max_iterations=max_iterations,
        )
    
    def generate_docs(
        self,
        entity: Dict[str, Any],
        dynamic_map: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate Part 2 documentation for a single entity."""
        context = build_part2_context(
            entity, dynamic_map, self.local_workdir, self.kodo_workdir
        )
        return run_doc_agent(self.agent, context)
