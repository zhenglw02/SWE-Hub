"""Bug/Issue generation step for each repo."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from bug_agent.pipeline.context import PipelineContext
from bug_agent.bug_issue_agent import BugIssueAgent
from bug_agent.prompts.k8s_bug_agent_prompt import SYSTEM_PROMPT as BUG_SYSTEM_PROMPT
from bug_agent.prompts.k8s_issue_agent_prompt import ISSUE_SYSTEM_PROMPT
from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
from code_data_agent.sandbox.sandbox_k8s import SandboxK8s
from code_data_agent.sandbox.scripts import (
    SCRIPT_BASH_FUNC,
    SCRIPT_NAVIGATOR,
    SCRIPT_FILE_EDITOR,
    SCRIPT_SEARCH_FUNC,
)
from code_data_agent.tools.tool_bash_executor import ToolBashExecutor
from code_data_agent.tools.tool_file_editor import ToolFileEditor
from code_data_agent.tools.tool_search import ToolSearch
from code_data_agent.tools.tool_get_hotspots import ToolGetHotspots
from code_data_agent.tools.tool_inspect_symbol import ToolInspectSymbol
from code_data_agent.tools.tool_run_test_oracle import ToolRunTestOracle
from code_data_agent.tools.tool_stop import ToolStop
from code_data_agent.tools.tool_reset import ToolReset


class BugIssueStep:
    """Run BugIssueAgent for each repo using preprocessed metadata."""

    def __init__(
        self,
        kubeconfig_path: Optional[str],
        namespace: str,
        pod_prefix: str,
        cpu_request: str,
        memory_request: str,
        run_timeout: int,
        env: Dict[str, str],
        llm_base_url: str,
        llm_model: str,
        llm_auth_token: str,
        work_dir: str = "/testbed",
        continue_on_error: bool = False,
        skip_existing: bool = False,
    ):
        """__init__."""
        self.kubeconfig_path = kubeconfig_path
        self.namespace = namespace
        self.pod_prefix = pod_prefix
        self.cpu_request = cpu_request
        self.memory_request = memory_request
        self.run_timeout = run_timeout
        self.env = env
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.llm_auth_token = llm_auth_token
        self.work_dir = work_dir
        self.continue_on_error = continue_on_error
        self.skip_existing = skip_existing

    def run(self, context: PipelineContext) -> None:
        """run."""
        context.log_progress("BugIssue", f"Processing {len(context.meta_list)} repos")
        output_dir = context.get_bug_issue_output_dir()
        os.makedirs(output_dir, exist_ok=True)

        for idx, meta in enumerate(context.meta_list):
            repo = meta.get("repo") or f"line_{idx}"
            output_path = context.get_bug_issue_output_path(repo)
            if self.skip_existing and os.path.exists(output_path):
                continue
            try:
                result = self._process_single(meta)
                self._save_result(output_path, result)
            except Exception as exc:
                context.add_error(f"BugIssue failed for {repo}: {exc}")
                if not self.continue_on_error:
                    raise

    def _process_single(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        """_process_single."""
        repo = meta.get("repo")
        image_name = meta.get("image_name")
        pytest_command = meta.get("pytest_command")
        analyze_report_path = meta.get("analyze_report_path")
        ground_truth_path = meta.get("ground_truth_path")

        if not repo or not image_name or not pytest_command:
            raise ValueError("missing required fields: repo/image_name/pytest_command")
        if not analyze_report_path or not ground_truth_path:
            raise ValueError("missing preprocess fields: analyze_report_path/ground_truth_path")

        sandbox = self._init_sandbox(repo, image_name)
        try:
            self._init_git_baseline(sandbox)

            bug_tools = [
                ToolBashExecutor(),
                ToolFileEditor(),
                ToolSearch(),
                ToolGetHotspots(analyze_report_path=analyze_report_path),
                ToolInspectSymbol(analyze_report_path=analyze_report_path),
                ToolRunTestOracle(work_dir=self.work_dir, ground_truth_path=ground_truth_path),
                ToolStop(),
                ToolReset(),
            ]

            issue_tools = [
                ToolBashExecutor(),
                ToolSearch(),
                ToolInspectSymbol(analyze_report_path=analyze_report_path),
                ToolRunTestOracle(work_dir=self.work_dir, ground_truth_path=ground_truth_path),
                ToolStop(),
            ]

            llm_server = LLMServerHTTP(
                base_url=self.llm_base_url,
                model=self.llm_model,
                headers={"Authorization": f"Bearer {self.llm_auth_token}"},
            )

            bug_issue_agent = BugIssueAgent(
                bug_system_prompt=BUG_SYSTEM_PROMPT,
                issue_system_prompt=ISSUE_SYSTEM_PROMPT,
                bug_tools=bug_tools,
                issue_tools=issue_tools,
                llm_server=llm_server,
                sandbox=sandbox,
                ground_truth_path=ground_truth_path,
                work_dir=self.work_dir,
                bug_max_iterations=150,
                issue_max_iterations=50,
            )

            prompt = (
                "When calling run_test_oracle, the command should be "
                f"'{pytest_command}' \n You can only call one tool at a time. "
            )

            result = bug_issue_agent.run(prompt=prompt)
            output = dict(meta)
            output.update(result.to_dict())
            return output
        finally:
            sandbox.close()

    def _init_sandbox(self, repo: str, image_name: str) -> SandboxK8s:
        """_init_sandbox."""
        scripts = [
            SCRIPT_BASH_FUNC,
            SCRIPT_SEARCH_FUNC,
            SCRIPT_FILE_EDITOR,
            SCRIPT_NAVIGATOR,
        ]
        pod_name = self._build_pod_name(repo)
        return SandboxK8s(
            pod_name=pod_name,
            namespace=self.namespace,
            kubeconfig_path=self.kubeconfig_path,
            enveriment=self.env,
            image=image_name,
            cpu_request=self.cpu_request,
            memory_request=self.memory_request,
            workdir=self.work_dir,
            conda_dir="/opt/miniconda3",
            conda_env="base",
            python_bin="python3",
            scripts=scripts,
            run_timeout=self.run_timeout,
        )

    def _init_git_baseline(self, sandbox: SandboxK8s) -> None:
        """_init_git_baseline."""
        sandbox.run_command("git config --global user.email 'env_setup@system'")
        sandbox.run_command("git config --global user.name 'EnvSetup'")
        sandbox.run_command("cd /testbed && git add -A")
        sandbox.run_command(
            "cd /testbed && git commit -m 'Environment Setup Baseline' --allow-empty"
        )
        sandbox.run_command("cd /testbed && git rev-parse HEAD > .agent_baseline_sha")

    def _build_pod_name(self, repo: str) -> str:
        """_build_pod_name."""
        import random

        safe_id = repo.replace(".", "_").replace("__", "-").replace("_", "-").lower()
        random_suffix = random.randint(1000, 9999)
        pod_name = f"{self.pod_prefix}-{safe_id}-{random_suffix}"
        if len(pod_name) > 48:
            pod_name = f"{pod_name[:44]}-{random_suffix}"
        return pod_name

    def _save_result(self, output_path: str, result: Dict[str, Any]) -> None:
        """_save_result."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
