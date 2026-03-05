"""Data structures describing tool invocation status and results."""

from typing import Any, Dict, Optional

TOOL_INVOKER_STATUS_SUCCESS = "SUCCESS"
TOOL_INVOKER_STATUS_FAIL = "FAIL"


class ToolInvokeResult(object):
    """Represents the outcome of invoking a tool inside the agent."""

    def __init__(
        self,
        status: str,
        content: str,
        need_call_llm: bool,
        extra_data: Optional[Dict[str, Any]] = None,
    ):
        """Store whether the tool succeeded along with human-readable output.
        
        Args:
            status: Status of the tool invocation (SUCCESS or FAIL)
            content: Human-readable output string for AI to reference
            need_call_llm: Whether to continue calling LLM after this tool
            extra_data: Optional structured data for programmatic use
        """
        self.status = status
        # 字符串格式，AI主要参考的结果
        self.content = content
        # 是否需要在执行完成后再次调用llm处理
        self.need_call_llm = need_call_llm
        # 额外的结构化数据，供程序使用
        self.extra_data = extra_data or {}

    def to_dict(self) -> dict:
        """Serialize the result into a JSON-friendly dict."""
        result = {"status": self.status, "content": self.content}
        if self.extra_data:
            result["extra_data"] = self.extra_data
        return result
