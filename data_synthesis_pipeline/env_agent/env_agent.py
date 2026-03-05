"""EnvAgent: automated environment setup agent."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from code_data_agent.agent.agent import Agent
from code_data_agent.llm_server.llm_server_base import LLMServerBase
from code_data_agent.model.agent import (
    AgentRunResult,
    STOP_REASON_AGENT_STOP,
    STOP_REASON_MAX_ITERATION,
    STOP_REASON_TOOL_STOP,
)
from code_data_agent.model.llm_server import Message
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


# Status constants
STATUS_SUCCESS = "success"
STATUS_MAX_ITERATION = "max_iteration"
STATUS_TOOL_STOP = "tool_stop"
STATUS_ERROR = "error"


@dataclass
class EnvAgentResult:
    """Result of a single EnvAgent run."""

    env_status: str  # success | max_iteration | tool_stop | error
    install_script: Optional[str] = None
    test_script: Optional[str] = None
    summary: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "env_status": self.env_status,
            "install_script": self.install_script,
            "test_script": self.test_script,
            "summary": self.summary,
            "messages": [msg.to_dict() for msg in self.messages],
            "error": self.error,
        }


class EnvAgent:
    """Agent that sets up the development environment for a repository.

    The agent is given a K8s sandbox with the source code already copied to
    /testbed. It explores the project, installs dependencies, verifies that
    tests run, and then stops calling tools while outputting the final
    install_script and test_script as plain text (same pattern as bug_agent).

    Stop conditions:
    - AGENT_STOP (LLM outputs final answer without calling any tool) → success,
      parse install_script / test_script from the last assistant message.
    - TOOL_STOP (STOP tool called) → failure.
    - MAX_ITERATION → failure.
    """

    def __init__(
        self,
        system_prompt: str,
        tools: List[ToolBase],
        llm_server: LLMServerBase,
        sandbox: SandboxBase,
        max_iterations: int = 100,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = tools
        self.llm_server = llm_server
        self.sandbox = sandbox
        self.max_iterations = max_iterations

    def run(self, prompt: str = "") -> EnvAgentResult:
        """Run the environment-setup agent loop.

        Args:
            prompt: Initial user-turn message.

        Returns:
            EnvAgentResult with status and extracted scripts.
        """
        print("=" * 50)
        print("EnvAgent: starting environment setup...")
        print("=" * 50)

        agent = Agent(
            system_prompt=self.system_prompt,
            tools=self.tools,
            llm_server=self.llm_server,
            sandbox=self.sandbox,
            max_iterations=self.max_iterations,
        )

        run_result: AgentRunResult = agent.run(prompt=prompt)
        result = EnvAgentResult(env_status=STATUS_ERROR, messages=run_result.messages)

        if run_result.stop_reason == STOP_REASON_MAX_ITERATION:
            print("EnvAgent: reached max iterations")
            result.env_status = STATUS_MAX_ITERATION
            return result

        if run_result.stop_reason == STOP_REASON_TOOL_STOP:
            # STOP tool was called — agent declared failure
            print(f"EnvAgent: stopped by tool — {run_result.stop_tools}")
            result.env_status = STATUS_TOOL_STOP
            result.error = f"Agent stopped by tool: {run_result.stop_tools}"
            return result

        if run_result.stop_reason == STOP_REASON_AGENT_STOP:
            # LLM produced a final text response without calling any tool.
            # This is the success path: parse scripts from the last message.
            print("EnvAgent: LLM finished (AGENT_STOP) — extracting scripts")
            last_content = self._last_assistant_content(run_result.messages)
            install_script = self._extract_tag(last_content, "install_script")
            test_script = self._extract_tag(last_content, "test_script")

            if install_script and test_script:
                result.env_status = STATUS_SUCCESS
                result.install_script = install_script
                result.test_script = test_script
                result.summary = last_content
                print(
                    f"EnvAgent: success — "
                    f"install_script={len(install_script)} chars, "
                    f"test_script={len(test_script)} chars"
                )
            else:
                # LLM stopped but did not produce valid scripts
                result.env_status = STATUS_TOOL_STOP
                result.error = (
                    "Agent finished without producing valid "
                    "<install_script> / <test_script> tags"
                )
                print(f"EnvAgent: {result.error}")

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _last_assistant_content(self, messages: List[Message]) -> str:
        """Return the content of the last assistant message."""
        for msg in reversed(messages):
            if msg.role == "assistant" and msg.content:
                return msg.content
        return ""

    def _extract_tag(self, text: str, tag: str) -> Optional[str]:
        """Extract content inside <tag>...</tag> from text."""
        match = re.search(
            rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE
        )
        return match.group(1).strip() if match else None
