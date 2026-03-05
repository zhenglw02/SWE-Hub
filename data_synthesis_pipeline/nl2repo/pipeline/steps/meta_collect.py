"""Meta collection step - parses test results and builds metadata."""

import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm

from nl2repo.pipeline.context import PipelineContext
from nl2repo.models.task import MetaInfo, TestCaseStatus


def parse_pytest_xml_report(
    xml_file_path: str,
) -> Tuple[Optional[List[str]], Optional[List[str]], Optional[List[str]]]:
    """Parse pytest JUnit XML report.
    
    Args:
        xml_file_path: Path to test_report.xml
        
    Returns:
        Tuple of (passed_tests, failed_tests, skipped_tests) or (None, None, None) on error
    """
    if not os.path.exists(xml_file_path):
        return None, None, None
    
    passed_tests: List[str] = []
    failed_tests: List[str] = []
    skipped_tests: List[str] = []
    
    try:
        with open(xml_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Remove [STDOUT] prefix if present
        if lines and lines[0].strip() == "[STDOUT]":
            content = "".join(lines[1:])
        else:
            content = "".join(lines)
        
        if not content.strip():
            return [], [], []
        
        root = ET.fromstring(content)
        
        for testcase in root.iter("testcase"):
            classname = testcase.get("classname")
            name = testcase.get("name")
            
            if not name:
                continue
            
            full_test_name = f"{classname}::{name}"
            
            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped = testcase.find("skipped")
            
            if failure is not None or error is not None:
                failed_tests.append(full_test_name)
            elif skipped is not None:
                skipped_tests.append(full_test_name)
            else:
                passed_tests.append(full_test_name)
        
        return passed_tests, failed_tests, skipped_tests
        
    except ET.ParseError:
        return None, None, None
    except Exception as e:
        print(f"Error parsing {xml_file_path}: {e}")
        return None, None, None


class MetaCollectStep:
    """Collects and aggregates metadata from coverage runs.
    
    Parses XML test reports, aggregates test case status across
    multiple runs, and builds comprehensive metadata.
    """
    
    def __init__(self, num_runs: int = 10):
        """Initialize meta collect step.
        
        Args:
            num_runs: Number of coverage runs to aggregate
        """
        self.num_runs = num_runs
    
    def run(self, context: PipelineContext) -> None:
        """Execute metadata collection.
        
        Args:
            context: Pipeline context with meta_list and coverage_dir
        """
        context.log_progress("MetaCollect", f"Processing {len(context.meta_list)} repos")
        
        valid_metas: List[MetaInfo] = []
        
        for meta in tqdm(context.meta_list, desc="Collecting metadata", ncols=70):
            try:
                updated_meta = self.collect_single(meta, context)
                if updated_meta:
                    valid_metas.append(updated_meta)
            except Exception as e:
                context.add_error(f"Meta collection failed for {meta.repo}: {e}")
        
        # Update context with valid metas
        context.meta_list = valid_metas
        context.log_progress("MetaCollect", f"Collected {len(valid_metas)} valid repos")
        
        # Save updated metadata
        context.save_meta_list()
    
    def collect_single(
        self,
        meta: MetaInfo,
        context: PipelineContext,
    ) -> Optional[MetaInfo]:
        """Collect metadata for a single repository.
        
        Args:
            meta: Repository metadata
            context: Pipeline context
            
        Returns:
            Updated MetaInfo or None if invalid
        """
        result_dir = os.path.join(context.coverage_dir, meta.repo)
        test_case_status: Dict[str, List[str]] = defaultdict(list)
        
        coverage_path = None
        all_runs_valid = True
        
        for idx in range(self.num_runs):
            run_dir = os.path.join(result_dir, f"ground_truth_{idx:04d}")
            run_coverage = os.path.join(run_dir, "coverage.json")
            xml_path = os.path.join(run_dir, "test_report.xml")
            
            if not os.path.exists(xml_path) or not os.path.exists(run_coverage):
                all_runs_valid = False
                continue
            
            # Save last valid coverage path
            coverage_path = run_coverage
            
            # Parse test results
            passed, failed, _ = parse_pytest_xml_report(xml_path)
            
            if passed is None:
                continue
            
            for test_name in passed:
                test_case_status[test_name].append("PASSED")
            for test_name in failed:
                test_case_status[test_name].append("FAILED")
        
        if not all_runs_valid or coverage_path is None:
            return None
        
        # Aggregate test status
        test_case_result: Dict[str, str] = {}
        for test_name, statuses in test_case_status.items():
            if "FAILED" in statuses:
                test_case_result[test_name] = "FAILED"
            elif all(s == "PASSED" for s in statuses):
                test_case_result[test_name] = "PASSED"
            else:
                test_case_result[test_name] = "SKIPPED"
        
        # Update meta
        meta.test_case_result = test_case_result
        meta.coverage_path = coverage_path
        meta.local_repo_path = context.get_repo_local_path(meta.repo)
        
        return meta