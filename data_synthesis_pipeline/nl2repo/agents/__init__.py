"""Document generation agents for nl2repo pipeline."""

from nl2repo.agents.doc_agent import (
    DocPart1Agent,
    DocPart2Agent,
    create_doc_part1_tools,
    create_doc_part2_tools,
    run_doc_agent,
    build_part1_context,
    build_part2_context,
)
from nl2repo.agents.prompts import DOC_PART1_PROMPT, DOC_PART2_PROMPT

__all__ = [
    # Agent wrappers
    "DocPart1Agent",
    "DocPart2Agent",
    # Factory functions
    "create_doc_part1_tools",
    "create_doc_part2_tools",
    # Runner helpers
    "run_doc_agent",
    "build_part1_context",
    "build_part2_context",
    # Prompts
    "DOC_PART1_PROMPT",
    "DOC_PART2_PROMPT",
]