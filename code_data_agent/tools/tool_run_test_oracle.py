"""ToolRunTestOracle"""
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


class ToolRunTestOracle(ToolBase):
    """Tool RunTestOracle"""

    def __init__(self, work_dir: str, ground_truth_path: str = ""):
        """
        Initialize the tool.
        
        Args:
            work_dir: Working directory in the sandbox.
            ground_truth_path: Path to the ground-truth JSON file (on CFS).
                               If provided, LLM doesn't need to pass it.
        """
        self.work_dir = work_dir
        self._ground_truth_path = ground_truth_path
        super().__init__()

    def get_name(self) -> str:
        """Return the name of the tool."""
        return "RUN_TEST_ORACLE"

    def get_description(self) -> str:
        """Return a description of the tool."""
        return (
            "Execute the sanctioned test command inside the sandbox and compare the results against a ground-truth "
            "pytest report. Appends `--junitxml` automatically and surfaces Pass→Fail regressions."
        )

    def get_parameters(self) -> Dict[str, Any]:
        """Return a JSON schema that documents required parameters."""
        # 如果已预设路径，则LLM不需要传 ground_truth_path 参数
        if self._ground_truth_path:
            return {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Base command to execute (default: pytest).",
                        "default": "pytest",
                    },
                    "command_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of additional long-form CLI arguments, e.g. "
                            "['--maxfail=1', '--disable-warnings']. Only long options ('--foo') "
                            "and at most one positional argument are supported."
                        ),
                    },
                },
                "required": [],  # 没有必填参数了
            }
        else:
            return {
                "type": "object",
                "properties": {
                    "ground_truth_path": {
                        "type": "string",
                        "description": "Local path to the ground-truth JSON file (e.g. pytest report summary).",
                    },
                    "command": {
                        "type": "string",
                        "description": "Base command to execute (default: pytest).",
                        "default": "pytest",
                    },
                    "command_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of additional long-form CLI arguments, e.g. "
                            "['--maxfail=1', '--disable-warnings']. Only long options ('--foo') "
                            "and at most one positional argument are supported."
                        ),
                    },
                },
                "required": ["ground_truth_path"],
            }

    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """invoke."""
        # 优先使用预设路径，否则从参数获取
        ground_truth_path = self._ground_truth_path or kwargs.get("ground_truth_path")
        
        if not ground_truth_path or not os.path.exists(ground_truth_path):
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Invalid or missing ground_truth_path",
                need_call_llm=True,
            )

        command = kwargs.get("command") or "pytest"
        command_args = kwargs.get("command_args") or []
        xml_path = f"{self.work_dir.rstrip('/')}/pytest_report.xml"
        command_args.append(f"--junitxml={xml_path}")
        log_path = f"{self.work_dir.rstrip('/')}/pytest_log.txt"
        command_parts = [command] + command_args
        full_command = " ".join(command_parts) + " > " + log_path

        run_result = sandbox.run_command(full_command)
        if run_result.exit_code not in [0, 1]:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content=f"Sandboxed process terminated unexpectedly. [output]: \n{run_result.output}",
                need_call_llm=True,
            )

        xml_result = sandbox.run_command(f"cat {xml_path}")
        if xml_result.exit_code != 0:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content=f"Execution Error (Exit Code {xml_result.exit_code}). Potential Syntax Error or Missing Dependencies.\nStdout Tail:\n{xml_result.output[-800:]}",
                need_call_llm=False,
            )

        xml_content = xml_result.output or ""
        xml_start = xml_content.find("<?xml")
        if xml_start == -1:
            xml_start = xml_content.find("<testsuite")
        if xml_start == -1:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="XML report not found in output.",
                need_call_llm=False,
            )
        xml_content = xml_content[xml_start:]

        current_results = self._parse_xml_content(xml_content)
        gt_results = self._load_ground_truth(ground_truth_path)
        if not gt_results:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Error: Ground Truth file missing or invalid.",
                need_call_llm=False,
            )

        report = self._compare_results(gt_results, current_results)
        formatted = self._format_output_for_agent(report)
        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS, content=formatted, need_call_llm=True
        )


    def _parse_xml_content(self, content: str) -> Dict[str, Dict]:
        """
        解析 XML，提取状态和报错信息。
        返回: { "test_id": {"status": "FAILED", "msg": "AssertionError: ..."} }
        """
        results = {}
        try:
            # 容错处理：修补截断的 XML
            content = content.strip()
            if not content.endswith(">"):
                content += ">"

            root = ET.fromstring(content)

            for testcase in root.iter("testcase"):
                classname = testcase.get("classname")
                name = testcase.get("name")
                if not name:
                    continue

                # ID 格式需与 GT 保持一致 (通常是 classname::name)
                full_test_name = f"{classname}::{name}"

                failure = testcase.find("failure")
                error = testcase.find("error")

                status = "PASSED"
                msg = ""

                # return results
                if failure is not None:
                    status = "FAILED"
                    # 优先获取 text (XML 标签体)，这里通常包含完整的 traceback 和 diff
                    # get('message') 通常只有简短的一句话 "AssertionError: ..."
                    short_msg = failure.get("message", "")
                    long_msg = failure.text or ""

                    # 组合两者，确保信息不丢失
                    if long_msg:
                        msg = long_msg  # text 通常已经包含了 message 的内容
                    else:
                        msg = short_msg

                elif error is not None:
                    status = "ERROR"
                    msg = error.text or error.get("message") or "Unknown Error"

                if msg:
                    msg = msg.strip()

                results[full_test_name] = {"status": status, "msg": msg}

            return results
        except ET.ParseError as e:
            print(f"XML Parse Error: {e}")
            return {}

    def _load_ground_truth(self, path: str) -> Dict[str, str]:
        """加载 GT JSON: {"test_id": "PASSED"}"""
        if not path or not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _compare_results(self, gt: Dict[str, str], current: Dict[str, Dict]):
        """_compare_results."""
        p2f = []  # Pass -> Fail (Bug Injection Success)
        f2p = []  # Fail -> Pass (Accidental Fix)
        new_failures = []  # Not in GT but Failed

        for test_id, info in current.items():
            curr_status = info["status"]
            gt_status = gt.get(test_id)

            # Agent 只关心 FAILED/ERROR
            if curr_status in ["FAILED", "ERROR"]:
                if gt_status == "PASSED":
                    # 命中！这就是我们要的 P2F
                    p2f.append({"id": test_id, "msg": info["msg"]})
                # elif gt_status is None:
                #     # GT 里没有，算作新失败
                #     new_failures.append({"id": test_id, "msg": info['msg']})

            elif curr_status == "PASSED":
                if gt_status in ["FAILED", "ERROR"]:
                    # 意外修复
                    f2p.append(test_id)

        return {
            "p2f": p2f,
            "f2p": f2p,
            "new_failures": new_failures,
            "total": len(current),
        }

    def _format_output_for_agent(self, report):
        """
        生成自然语言报告。这是 Agent 真正看到的。
        """
        p2f = report["p2f"]
        new_failures = report["new_failures"]
        f2p = report["f2p"]

        lines = ["=== TEST EXECUTION REPORT ==="]

        # --- 情况 A: 成功注入 Bug (P2F) ---
        if p2f:
            lines.append(
                f"\n🎉 SUCCESS: You successfully introduced {len(p2f)} NEW failures (Pass -> Fail)!"
            )
            lines.append(
                "Here are the failure details. Use these to verify your bug and write the Issue report:"
            )

            # 限制显示数量，防止 Context 溢出
            for i, item in enumerate(p2f[:20], 1):
                lines.append(f"\n--- Failure {i}: {item['id']} ---")

                # 智能截取报错信息：取最后 500 字符，通常包含 assert 详情
                error_msg = item["msg"]
                if len(error_msg) > 1500:
                    error_msg = error_msg[:500] + "..." + error_msg[-1000:]

                lines.append(f"Error Log:\n{error_msg}")

        # --- 情况 B: 未知测试失败 (New Failures) ---
        # elif new_failures:
        #     lines.append(f"\n❓ UNCERTAIN: {len(new_failures)} failures found in tests NOT present in Ground Truth.")
        #     lines.append("This implies your changes might have broken something, but we can't be sure if these tests passed before.")
        #     lines.append("Details:")
        #     for item in new_failures[:2]:
        #         lines.append(f"- {item['id']}")

        # --- 情况 C: 无事发生 (Status Quo) ---
        else:
            lines.append("\n❌ RESULT: No new bugs detected.")
            lines.append(
                "All previously passing tests passed. Your change likely didn't affect the execution path of the tests."
            )

        # --- 警告: 意外修复 ---
        # if f2p:
        #     lines.append(f"\n⚠️ WARNING: You accidentally fixed {len(f2p)} existing bugs! (Fail -> Pass)")
        #     lines.append(f"Tests: {', '.join(f2p[:3])}...")

        return "\n".join(lines)