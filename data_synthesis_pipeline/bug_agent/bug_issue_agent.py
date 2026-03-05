"""BugIssueAgent: 组合Bug Agent和Issue Agent的完整流程"""

import json
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
from code_data_agent.tools.tool_gen_patch import ToolGenPatch
from code_data_agent.tools.tool_test_stats_collector import ToolTestStatsCollector


@dataclass
class BugIssueResult:
    """BugIssueAgent的运行结果"""
    
    # Bug Agent结果
    bug_status: str  # "success", "max_iteration", "tool_stop", "error"
    bug_summary: Optional[str] = None
    bug_messages: List[Message] = field(default_factory=list)
    
    # Patch和测试统计
    patch: Optional[str] = None
    test_stats: Optional[Dict[str, Any]] = None
    
    # Issue Agent结果
    issue_status: Optional[str] = None  # "success", "max_iteration", "tool_stop", "error", None
    issue_content: Optional[str] = None
    issue_messages: List[Message] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "bug_status": self.bug_status,
            "bug_summary": self.bug_summary,
            "bug_messages": [msg.to_dict() for msg in self.bug_messages],
            "patch": self.patch,
            "test_stats": self.test_stats,
            "issue_status": self.issue_status,
            "issue_content": self.issue_content,
            "issue_messages": [msg.to_dict() for msg in self.issue_messages],
        }


class BugIssueAgent:
    """组合Bug Agent和Issue Agent的完整流程"""
    
    def __init__(
        self,
        bug_system_prompt: str,
        issue_system_prompt: str,
        bug_tools: List[ToolBase],
        issue_tools: List[ToolBase],
        llm_server: LLMServerBase,
        sandbox: SandboxBase,
        ground_truth_path: str,
        work_dir: str = "/workspace",
        bug_max_iterations: int = 150,
        issue_max_iterations: int = 50,
    ):
        """
        初始化BugIssueAgent
        
        Args:
            bug_system_prompt: Bug Agent的系统提示词
            issue_system_prompt: Issue Agent的系统提示词模板（包含{context}占位符）
            bug_tools: Bug Agent可见的工具列表
            issue_tools: Issue Agent可见的工具列表
            llm_server: LLM服务器
            sandbox: 沙箱环境
            ground_truth_path: ground truth文件路径
            work_dir: 工作目录
            bug_max_iterations: Bug Agent最大迭代次数
            issue_max_iterations: Issue Agent最大迭代次数
        """
        self.bug_system_prompt = bug_system_prompt
        self.issue_system_prompt = issue_system_prompt
        self.bug_tools = bug_tools
        self.issue_tools = issue_tools
        self.llm_server = llm_server
        self.sandbox = sandbox
        self.ground_truth_path = ground_truth_path
        self.work_dir = work_dir
        self.bug_max_iterations = bug_max_iterations
        self.issue_max_iterations = issue_max_iterations
        
        # 内部工具实例（不暴露给LLM）
        self._patch_tool = ToolGenPatch()
        self._stats_tool = ToolTestStatsCollector(work_dir=work_dir)
    
    def run(self, prompt: str = "") -> BugIssueResult:
        """
        运行完整的Bug注入和Issue生成流程
        
        Args:
            prompt: 初始用户提示
            
        Returns:
            BugIssueResult: 包含整个流程的结果
        """
        result = BugIssueResult(bug_status="error")
        
        # ========== Phase 1: Bug Agent ==========
        print("=" * 50)
        print("Phase 1: Running Bug Agent...")
        print("=" * 50)
        
        bug_agent = Agent(
            system_prompt=self.bug_system_prompt,
            tools=self.bug_tools,
            llm_server=self.llm_server,
            sandbox=self.sandbox,
            max_iterations=self.bug_max_iterations,
        )
        
        bug_run_result = bug_agent.run(prompt=prompt)
        result.bug_messages = bug_run_result.messages
        
        # 解析Bug Agent的停止原因
        if bug_run_result.stop_reason == STOP_REASON_MAX_ITERATION:
            print("Bug Agent: 达到最大迭代次数")
            result.bug_status = "max_iteration"
            return result
        elif bug_run_result.stop_reason == STOP_REASON_TOOL_STOP:
            print(f"Bug Agent: 工具停止 - {bug_run_result.stop_tools}")
            result.bug_status = "tool_stop"
            # 如果是STOP工具，也继续执行后续流程
            if "STOP" in bug_run_result.stop_tools:
                return result
        elif bug_run_result.stop_reason == STOP_REASON_AGENT_STOP:
            print("Bug Agent: 正常结束")
            result.bug_status = "success"
        
        # 从最后一条assistant消息中提取summary
        result.bug_summary = self._extract_last_content(bug_run_result.messages)
        print(f"Bug Summary: {result.bug_summary[:200] if result.bug_summary else 'None'}...")
        
        # ========== Phase 2: 显式调用隐藏工具 ==========
        print("=" * 50)
        print("Phase 2: Generating Patch and Collecting Test Stats...")
        print("=" * 50)
        
        # 调用 GEN_PATCH
        patch_result = self._patch_tool.invoke(self.sandbox)
        result.patch = patch_result.content if patch_result.status == "SUCCESS" else None
        print(f"Patch generated: {len(result.patch) if result.patch else 0} chars")
        
        # 调用 TEST_STATS_COLLECTOR
        stats_result = self._stats_tool.invoke(
            self.sandbox, 
            ground_truth_path=self.ground_truth_path
        )
        if stats_result.status == "SUCCESS":
            try:
                result.test_stats = json.loads(stats_result.content)
            except json.JSONDecodeError:
                result.test_stats = {"raw": stats_result.content}
        print(f"Test stats collected: {result.test_stats is not None}")
        
        # 检查是否有有效的P2F
        if not self._has_valid_p2f(result.test_stats):
            print("Warning: No PASS2FAIL detected, but continuing to Issue Agent...")
        
        # ========== Phase 3: Issue Agent ==========
        print("=" * 50)
        print("Phase 3: Running Issue Agent...")
        print("=" * 50)
        
        # 构建Issue Agent的上下文
        context_str = self._build_issue_context(
            patch=result.patch,
            test_stats=result.test_stats,
            summary=result.bug_summary,
        )
        
        # 替换模板中的占位符
        issue_prompt = self.issue_system_prompt.replace("{context}", context_str)
        
        # 重置LLM Server的工具列表
        self.llm_server.add_tools(self.issue_tools)
        
        issue_agent = Agent(
            system_prompt=issue_prompt,
            tools=self.issue_tools,
            llm_server=self.llm_server,
            sandbox=self.sandbox,
            max_iterations=self.issue_max_iterations,
        )
        
        issue_run_result = issue_agent.run(prompt="")
        result.issue_messages = issue_run_result.messages
        
        # 解析Issue Agent的停止原因
        if issue_run_result.stop_reason == STOP_REASON_MAX_ITERATION:
            print("Issue Agent: 达到最大迭代次数")
            result.issue_status = "max_iteration"
        elif issue_run_result.stop_reason == STOP_REASON_TOOL_STOP:
            print(f"Issue Agent: 工具停止 - {issue_run_result.stop_tools}")
            result.issue_status = "tool_stop"
        elif issue_run_result.stop_reason == STOP_REASON_AGENT_STOP:
            print("Issue Agent: 正常结束")
            result.issue_status = "success"
        
        # 从最后一条assistant消息中提取issue内容
        result.issue_content = self._extract_last_content(issue_run_result.messages)
        print(f"Issue generated: {len(result.issue_content) if result.issue_content else 0} chars")
        
        return result
    
    def _extract_last_content(self, messages: List[Message]) -> Optional[str]:
        """从消息列表中提取最后一条assistant消息的内容"""
        for msg in reversed(messages):
            if msg.role == "assistant" and msg.content:
                return msg.content
        return None
    
    def _has_valid_p2f(self, test_stats: Optional[Dict[str, Any]]) -> bool:
        """检查测试统计中是否有有效的P2F"""
        if not test_stats:
            return False
        content = test_stats.get("content", test_stats)
        if isinstance(content, dict):
            summary = content.get("summary", {})
            return summary.get("p2f_count", 0) > 0
        return False
    
    def _build_issue_context(
        self,
        patch: Optional[str],
        test_stats: Optional[Dict[str, Any]],
        summary: Optional[str],
    ) -> str:
        """构建Issue Agent的上下文信息"""
        context_parts = []
        
        # 1. Patch
        context_parts.append("## Code Changes (Diff)")
        if patch:
            # 截断过长的patch
            patch_content = patch if len(patch) <= 10000 else patch[:10000] + "\n...(truncated)..."
            context_parts.append(f"```diff\n{patch_content}\n```")
        else:
            context_parts.append("No patch available.")
        
        # 2. Bug Summary
        context_parts.append("\n## Bug Agent Summary")
        if summary:
            context_parts.append(f"```text\n{summary}\n```")
        else:
            context_parts.append("No summary available.")
        
        # 3. Test Failures (P2F)
        context_parts.append("\n## Test Failures (Regressions)")
        if test_stats:
            content = test_stats.get("content", test_stats)
            if isinstance(content, dict):
                p2f_details = content.get("p2f_details", {})
                if p2f_details:
                    for test_id, msg in list(p2f_details.items())[:5]:  # 最多5个
                        # 截断过长的traceback
                        if len(msg) > 1000:
                            msg = msg[:500] + "\n...(truncated)..." + msg[-500:]
                        context_parts.append(f"### Test: {test_id}")
                        context_parts.append(f"```text\n{msg}\n```")
                else:
                    context_parts.append("No regression failures detected.")
            else:
                context_parts.append(f"Raw stats: {content}")
        else:
            context_parts.append("No test stats available.")
        
        return "\n".join(context_parts)