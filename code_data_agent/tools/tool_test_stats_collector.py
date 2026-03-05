"""Test Stats Collector"""

import json
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from code_data_agent.model.tool import (
    ToolInvokeResult,
    TOOL_INVOKER_STATUS_SUCCESS,
    TOOL_INVOKER_STATUS_FAIL,
)
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


class ToolTestStatsCollector(ToolBase):
    """Test Stats Collector"""

    def __init__(self, work_dir: str):
        """Initialize the tool."""
        self.work_dir = work_dir
        super().__init__()

    def get_name(self) -> str:
        """Return the name of the tool."""
        return "TEST_STATS_COLLECTOR"

    def get_description(self) -> str:
        """Return a description of the tool."""
        return (
            "Internal diagnostic tool that reads `/workspace/pytest_report.xml`, compares it with the provided "
            "ground-truth summary, and returns the current pass/fail breakdown plus Pass→Fail regression details."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Return the parameters of the tool."""
        return {
            "type": "object",
            "properties": {
                "ground_truth_path": {
                    "type": "string",
                    "description": "Path to the ground-truth JSON file generated from baseline pytest results.",
                }
            },
            "required": ["ground_truth_path"],
        }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """Invoke the tool with the given arguments."""
        ground_truth_path = kwargs.get("ground_truth_path")
        if not ground_truth_path or not os.path.exists(ground_truth_path):
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content=f"Ground Truth file missing: {ground_truth_path}",
                need_call_llm=True,
            )

        xml_result = sandbox.run_command(
            f"cat {self.work_dir.rstrip('/')}/pytest_report.xml", None
        )
        if xml_result.exit_code != 0:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Report XML not found or empty. Did the Bug Agent run tests?",
                need_call_llm=True,
            )

        xml_content = xml_result.output or ""
        xml_start = xml_content.find("<?xml")
        if xml_start == -1:
            xml_start = xml_content.find("<testsuite")
        if xml_start == -1:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Invalid XML format received.",
                need_call_llm=False,
            )

        xml_content = xml_content[xml_start:]
        current_results = self._parse_xml_content(xml_content)

        try:
            with open(ground_truth_path, "r", encoding="utf-8") as fh:
                gt_results = json.load(fh)
        except Exception as exc:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content=f"Failed to load GT json: {exc}",
                need_call_llm=False,
            )

        if not isinstance(gt_results, dict):
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Ground Truth JSON must be a dictionary.",
                need_call_llm=False,
            )

        report = self._summarize_results(gt_results, current_results)
        content = json.dumps(report, ensure_ascii=False, indent=2)
        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS, content=content, need_call_llm=True
        )

    def _summarize_results(
        self, gt_results: Dict[str, str], current_results: Dict[str, Dict[str, str]]
    ) -> Dict[str, Any]:
        """_summarize_results."""
        passed_tests = []
        failed_tests = []
        p2f_details = {}  # Key: Test ID, Value: Error Message

        for test_id, info in current_results.items():
            # [关键修改] 严格过滤：如果 GT 里没有这个测试，直接忽略（视为噪音/新测试）
            if test_id not in gt_results:
                continue

            curr_status = info["status"]
            gt_status = gt_results[test_id]  # 既然上面判断了 in，这里肯定有值

            # 分类 1: GT 中存在的且当前通过的
            if curr_status == "PASSED":
                passed_tests.append(test_id)

            # 分类 2: GT 中存在的且当前失败的
            elif curr_status in ["FAILED", "ERROR"]:
                failed_tests.append(test_id)

                # 分类 3: 筛选 P2F (Regression)
                # 只有当 GT 明确标记为 PASSED，而现在挂了，才算 Regression
                if gt_status == "PASSED":
                    p2f_details[test_id] = info["msg"]

        return {
            "status": "success",
            "content": {
                "summary": {
                    "total": len(gt_results),
                    "passed_count": len(passed_tests),
                    "failed_count": len(failed_tests),
                    "p2f_count": len(p2f_details),
                },
                "passed_tests": passed_tests,  # 列表
                "failed_tests": failed_tests,  # 列表
                "p2f_details": p2f_details,  # 字典 {id: msg}
            },
        }

    def _parse_xml_content(self, content: str) -> Dict[str, Dict]:
        """
        解析 XML，提取状态和详细报错。
        """
        results = {}
        try:
            # 容错处理
            content = content.strip()
            # 某些极端情况下 xml 截断可能导致 parse error，尝试补全结尾
            if content and not content.endswith(">"):
                # 这是一个简单的尝试，复杂的截断很难修
                if "</testsuite>" not in content[-20:]:
                    content += "</testsuite>"

            root = ET.fromstring(content)

            for testcase in root.iter("testcase"):
                classname = testcase.get("classname")
                name = testcase.get("name")
                if not name:
                    continue

                # ID 格式需与 GT 保持一致 (通常是 path/to/file.py::classname::methodname 或 file::func)
                # Pytest XML classname 通常是 file.path.Class
                # 这里的具体格式取决于你的 GT 是怎么生成的，需要保持一致
                # 假设 GT 是 file::class::method 格式，这里可能需要微调
                # 目前保持你原有的逻辑：
                full_test_name = f"{classname}::{name}"

                failure = testcase.find("failure")
                error = testcase.find("error")

                status = "PASSED"
                msg = ""

                if failure is not None:
                    status = "FAILED"
                    # 优先取 text (包含详细堆栈)，没有则取 message
                    msg = failure.text or failure.get("message", "")
                elif error is not None:
                    status = "ERROR"
                    msg = error.text or error.get("message", "")

                if msg:
                    msg = msg.strip()

                results[full_test_name] = {"status": status, "msg": msg}

            return results
        except ET.ParseError as e:
            # 返回空字典而不是崩掉，让外层处理
            print(f"XML Parse Error: {e}")
            return {}
