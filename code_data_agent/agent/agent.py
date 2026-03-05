"""Agent"""

import json
import logging
import sys
from typing import Dict, List

from code_data_agent.llm_server.llm_server_base import LLMServerBase
from code_data_agent.model.llm_server import Message, ROLE_SYSTEM, ROLE_USER, ROLE_TOOL
from code_data_agent.model.agent import (
    AgentRunResult,
    STOP_REASON_AGENT_STOP,
    STOP_REASON_MAX_ITERATION,
    STOP_REASON_TOOL_STOP,
)
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class Agent:
    """Agent"""
    def __init__(
        self,
        system_prompt: str,
        tools: List[ToolBase],
        llm_server: LLMServerBase,
        sandbox: SandboxBase,
        max_iterations: int = 150,
    ):
        """Initialize the agent."""
        self.system_prompt = system_prompt
        self.llm_server = llm_server
        self.sandbox = sandbox
        self.tool_map = self._build_tool_map(tools)
        self.llm_server.add_tools(tools)
        self.max_iterations = max_iterations

    def run(self, prompt: str = "") -> AgentRunResult:
        """Run the agent with the given prompt."""
        messages: List[Message] = []
        if self.system_prompt:
            system_message = Message(role=ROLE_SYSTEM, content=self.system_prompt)
            messages.append(system_message)
            self._log_message(system_message)

        if prompt:
            prompt_message = Message(role=ROLE_USER, content=prompt)
            messages.append(prompt_message)
            self._log_message(prompt_message)

        try:
            for i in range(self.max_iterations):
                response_message = self.llm_server.handle_message(messages)
                messages.append(response_message)
                self._log_message(response_message)

                tool_calls = response_message.tool_calls or []
                if not tool_calls:
                    return AgentRunResult(stop_reason=STOP_REASON_AGENT_STOP, messages=messages)

                should_continue = False
                stop_tools = []
                for call in tool_calls:
                    tool_name = (call.get("function") or {}).get("name")
                    raw_args = (call.get("function") or {}).get("arguments")
                    tool_args = self._parse_tool_args(raw_args)

                    tool = self.tool_map.get(tool_name)
                    if not tool:
                        tool_invoke_message = Message(
                            role=ROLE_TOOL,
                            content=f"Unknown tool: {tool_name}",
                            tool_call_id=call.get("id"),
                            name=tool_name,
                        )
                        messages.append(tool_invoke_message)
                        self._log_message(tool_invoke_message)

                    result = tool.invoke(self.sandbox, **tool_args)
                    content = json.dumps(result.to_dict())
                    tool_invoke_message = Message(
                        role=ROLE_TOOL,
                        content=content,
                        tool_call_id=call.get("id"),
                        name=tool_name,
                    )
                    messages.append(tool_invoke_message)
                    self._log_message(tool_invoke_message)

                    if result.need_call_llm:
                        should_continue = True
                    else:
                        stop_tools.append(tool.get_name())

                if not should_continue:
                    return AgentRunResult(stop_reason=STOP_REASON_TOOL_STOP, stop_tools=stop_tools, messages=messages)

            return AgentRunResult(stop_reason=STOP_REASON_MAX_ITERATION, messages=messages)

        except Exception as exc:
            raise exc

    def _build_tool_map(self, tools: List[ToolBase]) -> Dict[str, ToolBase]:
        """Build a map of tools by name."""
        return {tool.get_name(): tool for tool in tools}

    def _parse_tool_args(self, raw_args) -> dict:
        """Parse tool arguments."""
        if raw_args is None:
            return {}
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                return json.loads(raw_args)
            except json.JSONDecodeError:
                print(f"[Agent:_parse_tool_args]: Invalid JSON format: {raw_args}")
                pass
        return {}

    def _log_message(self, message: Message) -> None:
        """Log every message exchange in JSON format."""
        logger.info(json.dumps(message.to_dict(), ensure_ascii=False, indent=2))
