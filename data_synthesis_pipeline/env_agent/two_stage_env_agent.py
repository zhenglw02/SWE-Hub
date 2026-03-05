"""TwoStageEnvAgent: two-pass env setup for JS/TS repos with messy test frameworks.

Stage 1 — install only:  runs an Agent loop on the same sandbox, stops when the
          LLM outputs <install_script> without calling any tool.

Stage 2 — test script:   clears the conversation history, runs a second Agent loop
          on the SAME sandbox (so the installed environment is still there), stops
          when the LLM outputs <test_script> without calling any tool.

Uses the code_data_agent SDK (Agent / LLMServerHTTP / SandboxBase / ToolBase).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from code_data_agent.agent.agent import Agent
from code_data_agent.llm_server.llm_server_base import LLMServerBase
from code_data_agent.model.agent import (
    STOP_REASON_AGENT_STOP,
    STOP_REASON_MAX_ITERATION,
    STOP_REASON_TOOL_STOP,
)
from code_data_agent.model.llm_server import Message
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


# Status constants (same as EnvAgentResult for consistency)
STATUS_SUCCESS = "success"
STATUS_MAX_ITERATION = "max_iteration"
STATUS_TOOL_STOP = "tool_stop"
STATUS_STAGE1_FAILED = "stage1_failed"


@dataclass
class TwoStageEnvAgentResult:
    """Combined result of both stages."""

    env_status: str       # success | max_iteration | tool_stop | stage1_failed
    install_script: Optional[str] = None
    test_script: Optional[str] = None

    # Per-stage details
    stage1_status: Optional[str] = None
    stage2_status: Optional[str] = None
    stage1_messages: List[Message] = field(default_factory=list)
    stage2_messages: List[Message] = field(default_factory=list)

    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """to dict"""
        return {
            "env_status": self.env_status,
            "install_script": self.install_script,
            "test_script": self.test_script,
            "stage1_status": self.stage1_status,
            "stage2_status": self.stage2_status,
            "stage1_messages": [m.to_dict() for m in self.stage1_messages],
            "stage2_messages": [m.to_dict() for m in self.stage2_messages],
            "error": self.error,
        }


class TwoStageEnvAgent:
    """Two-pass environment setup agent (JS/TS use case).

    Uses the same sandbox for both stages so that packages installed in
    Stage 1 are available when Stage 2 generates the test script.
    Message history is cleared between stages (fresh context per Agent).

    Mirrors BugIssueAgent in structure:
      Stage 1 → Agent(stage1_prompt, stage1_tools)
      Stage 2 → Agent(stage2_prompt, stage2_tools)   [same sandbox]
    """

    def __init__(
        self,
        stage1_system_prompt: str,
        stage2_system_prompt: str,
        stage1_tools: List[ToolBase],
        stage2_tools: List[ToolBase],
        llm_server: LLMServerBase,
        sandbox: SandboxBase,
        stage1_max_iterations: int = 100,
        stage2_max_iterations: int = 60,
    ) -> None:
        self.stage1_system_prompt = stage1_system_prompt
        self.stage2_system_prompt = stage2_system_prompt
        self.stage1_tools = stage1_tools
        self.stage2_tools = stage2_tools
        self.llm_server = llm_server
        self.sandbox = sandbox
        self.stage1_max_iterations = stage1_max_iterations
        self.stage2_max_iterations = stage2_max_iterations

    def run(
        self,
        stage1_prompt: str = "",
        stage2_prompt: str = "",
    ) -> TwoStageEnvAgentResult:
        """Run Stage 1 then (if successful) Stage 2 on the same sandbox."""
        result = TwoStageEnvAgentResult(env_status=STATUS_STAGE1_FAILED)

        # ── Stage 1: Install ──────────────────────────────────────────
        print("=" * 50)
        print("TwoStageEnvAgent — Stage 1: Installing dependencies...")
        print("=" * 50)

        stage1_agent = Agent(
            system_prompt=self.stage1_system_prompt,
            tools=self.stage1_tools,
            llm_server=self.llm_server,
            sandbox=self.sandbox,
            max_iterations=self.stage1_max_iterations,
        )
        s1_run = stage1_agent.run(prompt=stage1_prompt)
        result.stage1_messages = s1_run.messages

        install_script, s1_status = self._extract_single_tag(
            s1_run, "install_script", "Stage 1"
        )
        result.stage1_status = s1_status

        if s1_status != STATUS_SUCCESS or not install_script:
            result.env_status = STATUS_STAGE1_FAILED
            result.error = f"Stage 1 failed ({s1_status}): no install_script produced"
            print(f"TwoStageEnvAgent: {result.error}")
            return result

        result.install_script = install_script
        print(
            f"TwoStageEnvAgent — Stage 1 success: "
            f"install_script={len(install_script)} chars"
        )

        # ── Stage 2: Test Script ──────────────────────────────────────
        print("=" * 50)
        print("TwoStageEnvAgent — Stage 2: Generating test script...")
        print("=" * 50)

        # Re-register Stage 2 tools with the LLM server (clears Stage 1 tools)
        self.llm_server.add_tools(self.stage2_tools)

        stage2_agent = Agent(
            system_prompt=self.stage2_system_prompt,
            tools=self.stage2_tools,
            llm_server=self.llm_server,
            sandbox=self.sandbox,
            max_iterations=self.stage2_max_iterations,
        )
        s2_run = stage2_agent.run(prompt=stage2_prompt)
        result.stage2_messages = s2_run.messages

        test_script, s2_status = self._extract_single_tag(
            s2_run, "test_script", "Stage 2"
        )
        result.stage2_status = s2_status

        if s2_status != STATUS_SUCCESS or not test_script:
            result.env_status = s2_status or STATUS_TOOL_STOP
            result.error = f"Stage 2 failed ({s2_status}): no test_script produced"
            print(f"TwoStageEnvAgent: {result.error}")
            return result

        result.test_script = test_script
        result.env_status = STATUS_SUCCESS
        print(
            f"TwoStageEnvAgent — Stage 2 success: "
            f"test_script={len(test_script)} chars"
        )
        return result

    # ── Internal helpers ──────────────────────────────────────────────

    def _extract_single_tag(
        self, run_result, tag: str, stage_label: str
    ):
        """
        Determine status from run_result and extract <tag> from the last
        assistant message.

        Returns (extracted_content_or_None, status_string).
        """
        from code_data_agent.model.agent import (
            STOP_REASON_AGENT_STOP,
            STOP_REASON_MAX_ITERATION,
            STOP_REASON_TOOL_STOP,
        )

        if run_result.stop_reason == STOP_REASON_MAX_ITERATION:
            print(f"{stage_label}: reached max iterations")
            return None, STATUS_MAX_ITERATION

        if run_result.stop_reason == STOP_REASON_TOOL_STOP:
            print(f"{stage_label}: stopped by tool — {run_result.stop_tools}")
            return None, STATUS_TOOL_STOP

        if run_result.stop_reason == STOP_REASON_AGENT_STOP:
            last_content = self._last_assistant_content(run_result.messages)
            extracted = self._extract_tag(last_content, tag)
            if extracted:
                return extracted, STATUS_SUCCESS
            else:
                print(f"{stage_label}: LLM finished but no <{tag}> tag found")
                return None, STATUS_TOOL_STOP

        return None, STATUS_TOOL_STOP

    def _last_assistant_content(self, messages: List[Message]) -> str:
        for msg in reversed(messages):
            if msg.role == "assistant" and msg.content:
                return msg.content
        return ""

    def _extract_tag(self, text: str, tag: str) -> Optional[str]:
        match = re.search(
            rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE
        )
        return match.group(1).strip() if match else None
