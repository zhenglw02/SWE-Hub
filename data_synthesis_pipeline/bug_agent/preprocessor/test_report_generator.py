"""
测试报告生成器：在Sandbox中运行pytest并生成测试报告

工作流程：
1. Sandbox中执行pytest，直接将xml输出到CFS路径
2. 本地读取CFS上的xml文件
3. 本地解析xml并保存json到CFS

注意：Sandbox需要挂载CFS，这样输出路径对Sandbox和本地都可访问。
"""

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from code_data_agent.sandbox.sandbox_base import SandboxBase


@dataclass
class TestReportResult:
    """测试报告生成结果"""
    success: bool
    xml_path: Optional[str] = None
    json_path: Optional[str] = None
    summary: Optional[Dict] = None
    error_message: Optional[str] = None


class TestReportGenerator:
    """测试报告生成器"""

    def __init__(self, sandbox: SandboxBase):
        """
        初始化生成器
        
        Args:
            sandbox: Sandbox实例
        """
        self.sandbox = sandbox
    
    def generate(
        self,
        pytest_command: str,
        output_dir: str,
        repo_name: str,
    ) -> TestReportResult:
        """
        运行pytest并生成测试报告
        
        Args:
            pytest_command: pytest命令（不包含--junitxml参数）
            output_dir: 输出目录（CFS路径，Sandbox和本地都可访问）
            repo_name: 仓库名称（用于生成文件名）
            
        Returns:
            TestReportResult: 生成结果
        """
        # 输出路径（CFS上，Sandbox和本地都可访问）
        xml_path = os.path.join(output_dir, f"{repo_name}_pytest.xml")
        log_path = os.path.join(output_dir, f"{repo_name}_pytest.log")
        json_path = os.path.join(output_dir, f"{repo_name}_test_report.json")
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # 1. Sandbox中执行pytest，直接输出到CFS路径
            full_command = f"cd /testbed && {pytest_command} --junitxml={xml_path} > {log_path} 2>&1"
            run_result = self.sandbox.run_command(full_command)
            
            # Pytest exit code: 0=Pass, 1=Fail, 2=Interrupted, 3=InternalError, 4=UsageError, 5=NoTestsFound
            if run_result.exit_code not in [0, 1]:
                return TestReportResult(
                    success=False,
                    error_message=f"Pytest execution failed (Exit Code {run_result.exit_code}). Check log: {log_path}",
                )
            
            # 2. 本地读取CFS上的xml文件
            if not os.path.exists(xml_path):
                return TestReportResult(
                    success=False,
                    error_message=f"XML file not found at {xml_path}",
                )
            
            with open(xml_path, "r", encoding="utf-8") as f:
                xml_content = f.read()
            
            # 3. 本地解析XML
            parsed_data = self._parse_pytest_xml(xml_content)
            
            if parsed_data is None:
                return TestReportResult(
                    success=False,
                    error_message="Failed to parse pytest XML",
                )
            
            # 4. 本地保存json到CFS
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(parsed_data, f, ensure_ascii=False, indent=2)
            
            # 5. 生成摘要
            summary = self._count_status(parsed_data)
            
            return TestReportResult(
                success=True,
                xml_path=xml_path,
                json_path=json_path,
                summary=summary,
            )
            
        except Exception as e:
            return TestReportResult(
                success=False,
                error_message=str(e),
            )
    
    def _parse_pytest_xml(self, xml_content: str) -> Optional[Dict[str, str]]:
        """解析pytest XML输出"""
        # 清理内容
        xml_content = self._clean_xml_content(xml_content)
        if not xml_content:
            return None
        
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return None
        
        results: Dict[str, str] = {}
        for testcase in root.iter("testcase"):
            classname = testcase.get("classname")
            name = testcase.get("name")
            if not name or not classname:
                continue
            
            full_test_name = f"{classname}::{name}"
            
            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped = testcase.find("skipped")
            
            if failure is not None or error is not None:
                results[full_test_name] = "FAILED"
            elif skipped is not None:
                results[full_test_name] = "SKIPPED"
            else:
                results[full_test_name] = "PASSED"
        
        return results
    
    def _clean_xml_content(self, xml_content: str) -> Optional[str]:
        """清理XML内容"""
        if not xml_content:
            return None
        
        lines = xml_content.splitlines()
        if lines and "[STDOUT]" in lines[0]:
            xml_content = "\n".join(lines[1:])
        
        xml_content = xml_content.strip()
        if not xml_content:
            return None
        
        xml_start = xml_content.find("<?xml")
        if xml_start == -1:
            xml_start = xml_content.find("<testsuite")
        
        if xml_start != -1:
            xml_content = xml_content[xml_start:]
        else:
            return None
        
        if not xml_content.endswith(">"):
            xml_content += ">"
        
        return xml_content
    
    def _count_status(self, parsed: Dict[str, str]) -> Dict[str, int]:
        """统计测试状态"""
        counts = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0, "TOTAL": len(parsed)}
        for status in parsed.values():
            if status in counts:
                counts[status] += 1
        return counts