"""Preprocess step: generate test report + repo analysis for each repo."""

import os
from typing import Any, Dict, Optional

from bug_agent.pipeline.context import PipelineContext
from bug_agent.preprocessor.repo_analyzer import RepoAnalyzer
from bug_agent.preprocessor.test_report_generator import TestReportGenerator
from code_data_agent.sandbox.sandbox_k8s import SandboxK8s


class PreprocessStep:
    """Run pytest report generation and repo analysis for each repo."""

    def __init__(
        self,
        kubeconfig_path: Optional[str],
        namespace: str,
        pod_prefix: str,
        cpu_request: str,
        memory_request: str,
        run_timeout: int,
        env: Dict[str, str],
        skip_existing: bool = True,
        continue_on_error: bool = False,
    ):
        """__init__."""
        self.kubeconfig_path = kubeconfig_path
        self.namespace = namespace
        self.pod_prefix = pod_prefix
        self.cpu_request = cpu_request
        self.memory_request = memory_request
        self.run_timeout = run_timeout
        self.env = env
        self.skip_existing = skip_existing
        self.continue_on_error = continue_on_error

    def run(self, context: PipelineContext) -> None:
        """run."""
        context.log_progress("Preprocess", f"Processing {len(context.meta_list)} repos")

        for idx, meta in enumerate(context.meta_list):
            try:
                self._process_single(meta, context)
            except Exception as exc:
                context.add_error(f"Preprocess failed for line {idx}: {exc}")
                if not self.continue_on_error:
                    raise

    def _process_single(self, meta: Dict[str, Any], context: PipelineContext) -> None:
        """_process_single."""
        repo = meta.get("repo")
        image_name = meta.get("image_name")
        pytest_command = meta.get("pytest_command")
        local_repo_path = meta.get("reformat_path")

        if not repo or not image_name or not pytest_command or not local_repo_path:
            raise ValueError("missing required fields: repo/image_name/pytest_command/reformat_path")

        output_dir = context.get_report_dir(repo)
        os.makedirs(output_dir, exist_ok=True)

        default_ground_truth_path = os.path.join(output_dir, f"{repo}_test_report.json")
        default_analyze_report_path = os.path.join(output_dir, f"{repo}_analysis.json")

        ground_truth_path = meta.get("ground_truth_path") or default_ground_truth_path
        analyze_report_path = meta.get("analyze_report_path") or default_analyze_report_path

        if self.skip_existing and os.path.exists(ground_truth_path) and os.path.exists(analyze_report_path):
            meta["ground_truth_path"] = ground_truth_path
            meta["analyze_report_path"] = analyze_report_path
            return

        ground_truth_path = self._run_pytest_report(
            repo=repo,
            image_name=image_name,
            pytest_command=pytest_command,
            output_dir=output_dir,
        )

        analyze_report_path = self._run_repo_analyzer(
            repo=repo,
            repo_path=local_repo_path,
            output_dir=output_dir,
            test_report_path=ground_truth_path,
        )

        meta["ground_truth_path"] = ground_truth_path
        meta["analyze_report_path"] = analyze_report_path

    def _run_pytest_report(
        self,
        repo: str,
        image_name: str,
        pytest_command: str,
        output_dir: str,
    ) -> str:
        """_run_pytest_report."""
        sandbox = SandboxK8s(
            pod_name=self._build_pod_name(repo),
            namespace=self.namespace,
            kubeconfig_path=self.kubeconfig_path,
            image=image_name,
            enveriment=self.env,
            cpu_request=self.cpu_request,
            memory_request=self.memory_request,
            workdir="/workspace",
            conda_dir="/opt/miniconda3",
            conda_env="base",
            python_bin="python3",
            scripts=[],
            run_timeout=self.run_timeout,
        )
        try:
            generator = TestReportGenerator(sandbox)
            result = generator.generate(
                pytest_command=pytest_command,
                output_dir=output_dir,
                repo_name=repo,
            )
            if not result.success or not result.json_path:
                raise RuntimeError(result.error_message or "pytest report generation failed")
            return result.json_path
        finally:
            sandbox.close()

    def _run_repo_analyzer(
        self,
        repo: str,
        repo_path: str,
        output_dir: str,
        test_report_path: Optional[str],
    ) -> str:
        """_run_repo_analyzer."""
        analyzer = RepoAnalyzer(repo_path=repo_path, output_dir=output_dir)
        result = analyzer.analyze(
            repo_name=repo,
            test_report_path=test_report_path,
            config_path=None,
        )
        if not result.success or not result.output_path:
            raise RuntimeError(result.error_message or "repo analysis failed")
        return result.output_path

    def _build_pod_name(self, repo: str) -> str:
        """_build_pod_name."""
        # Align with nl2repo style: replace '.', '__', '_' then append random suffix and cap length.
        import random

        safe_id = repo.replace(".", "_").replace("__", "-").replace("_", "-").lower()
        random_suffix = random.randint(1000, 9999)
        pod_name = f"{self.pod_prefix}-{safe_id}-{random_suffix}"
        if len(pod_name) > 48:
            pod_name = f"{pod_name[:44]}-{random_suffix}"
        return pod_name
