"""Environment setup step: runs EnvAgent (one-stage) or TwoStageEnvAgent (two-stage)."""

import json
import os
import random
from pathlib import Path
from typing import Any, Dict, Optional

from env_agent.env_agent import EnvAgent
from env_agent.two_stage_env_agent import TwoStageEnvAgent
from env_agent.pipeline.context import PipelineContext
from env_agent.prompts.k8s_env_agent_prompt import SYSTEM_PROMPT as ONESTAGE_SYSTEM_PROMPT
from env_agent.prompts.k8s_env_stage1_prompt import STAGE1_SYSTEM_PROMPT
from env_agent.prompts.k8s_env_stage2_prompt import STAGE2_SYSTEM_PROMPT

from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
from code_data_agent.sandbox.sandbox_k8s import SandboxK8s
from code_data_agent.sandbox.scripts import (
    SCRIPT_BASH_FUNC,
    SCRIPT_FILE_EDITOR,
    SCRIPT_SEARCH_FUNC,
)
from code_data_agent.tools.tool_bash_executor import ToolBashExecutor
from code_data_agent.tools.tool_file_editor import ToolFileEditor
from code_data_agent.tools.tool_search import ToolSearch
from code_data_agent.tools.tool_stop import ToolStop


# Languages that need the two-stage approach (messy / unknown test frameworks)
_TWO_STAGE_LANGUAGES = {"javascript", "typescript", "js", "ts"}


class EnvSetupStep:
    """Pipeline step that runs an LLM agent to set up the repo environment.

    Language routing:
    - javascript / typescript → TwoStageEnvAgent
      Stage 1: install dependencies only
      Stage 2: discover test runner and generate test_script
    - python / java / others → EnvAgent (one-stage)
      Single loop: install + test_script in one pass

    For each repo in context.meta_list the step:
    1. Starts a K8s pod from the specified base image.
    2. Copies the local source tree into /testbed inside the pod.
    3. Runs the appropriate agent.
    4. Saves the result (install_script, test_script, messages) as a JSON file.
    """

    _SANDBOX_SCRIPTS = [SCRIPT_BASH_FUNC, SCRIPT_SEARCH_FUNC, SCRIPT_FILE_EDITOR]

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
        max_iterations: int = 100,
        stage2_max_iterations: int = 60,
        continue_on_error: bool = False,
        skip_existing: bool = False,
    ) -> None:
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
        self.max_iterations = max_iterations
        self.stage2_max_iterations = stage2_max_iterations
        self.continue_on_error = continue_on_error
        self.skip_existing = skip_existing

    # ── Public interface ──────────────────────────────────────────────

    def run(self, context: PipelineContext) -> None:
        """Process every repo in context.meta_list."""
        context.log_progress("EnvSetup", f"Processing {len(context.meta_list)} repos")
        output_dir = context.get_env_setup_output_dir()
        os.makedirs(output_dir, exist_ok=True)

        for idx, meta in enumerate(context.meta_list):
            repo = meta.get("repo") or meta.get("repo_name") or f"line_{idx}"
            output_path = context.get_env_setup_output_path(repo)

            if self.skip_existing and os.path.exists(output_path):
                context.log_progress(
                    "EnvSetup", f"[{idx+1}] Skipping {repo} (output exists)"
                )
                continue

            language = (meta.get("language") or "unknown").lower()
            mode = "two-stage" if language in _TWO_STAGE_LANGUAGES else "one-stage"
            context.log_progress(
                "EnvSetup",
                f"[{idx+1}/{len(context.meta_list)}] {repo}  language={language}  mode={mode}",
            )

            try:
                result = self._process_single(meta, language)
                self._save_result(output_path, result)
                context.log_progress(
                    "EnvSetup",
                    f"[{idx+1}] Done: {repo} => {result.get('env_status')}",
                )
            except Exception as exc:
                context.add_error(f"EnvSetup failed for {repo}: {exc}")
                if not self.continue_on_error:
                    raise

    # ── Per-repo processing ───────────────────────────────────────────

    def _process_single(self, meta: Dict[str, Any], language: str) -> Dict[str, Any]:
        """Set up environment for one repo; dispatch to one-stage or two-stage."""
        repo = meta.get("repo") or meta.get("repo_name")
        image_name = meta.get("image_name")
        reformat_path = meta.get("reformat_path")

        if not repo:
            raise ValueError("meta is missing 'repo' / 'repo_name'")
        if not image_name:
            raise ValueError(f"[{repo}] meta is missing 'image_name'")
        if not reformat_path:
            raise ValueError(f"[{repo}] meta is missing 'reformat_path'")

        sandbox = self._init_sandbox(repo, image_name)
        try:
            self._setup_workdir(sandbox, reformat_path)

            llm_server = LLMServerHTTP(
                base_url=self.llm_base_url,
                model=self.llm_model,
                headers={"Authorization": f"Bearer {self.llm_auth_token}"},
            )

            if language in _TWO_STAGE_LANGUAGES:
                agent_result = self._run_two_stage(repo, language, llm_server, sandbox)
            else:
                agent_result = self._run_one_stage(repo, language, llm_server, sandbox)

            output = dict(meta)
            output.update(agent_result)
            return output

        finally:
            sandbox.close()

    def _run_one_stage(
        self, repo: str, language: str, llm_server: LLMServerHTTP, sandbox: SandboxK8s
    ) -> Dict[str, Any]:
        """Single-loop agent: produces both install_script and test_script."""
        tools = [
            ToolBashExecutor(),
            ToolSearch(),
            ToolFileEditor(),
            ToolStop(),
        ]
        system_prompt = (
            ONESTAGE_SYSTEM_PROMPT
            .replace("{repo_name}", repo)
            .replace("{language}", language)
        )
        agent = EnvAgent(
            system_prompt=system_prompt,
            tools=tools,
            llm_server=llm_server,
            sandbox=sandbox,
            max_iterations=self.max_iterations,
        )
        prompt = (
            f"Set up the development environment for '{repo}' at {self.work_dir}. "
            "Call only ONE tool per turn. "
            "When done, stop calling tools and output <install_script> and <test_script>."
        )
        return agent.run(prompt=prompt).to_dict()

    def _run_two_stage(
        self, repo: str, language: str, llm_server: LLMServerHTTP, sandbox: SandboxK8s
    ) -> Dict[str, Any]:
        """Two-loop agent: Stage 1 installs, Stage 2 generates test_script."""
        stage1_tools = [
            ToolBashExecutor(),
            ToolSearch(),
            ToolFileEditor(),
            ToolStop(),
        ]
        stage2_tools = [
            ToolBashExecutor(),
            ToolSearch(),
            ToolStop(),
        ]

        s1_prompt_text = (
            STAGE1_SYSTEM_PROMPT
            .replace("{repo_name}", repo)
            .replace("{language}", language)
        )
        s2_prompt_text = (
            STAGE2_SYSTEM_PROMPT
            .replace("{repo_name}", repo)
            .replace("{language}", language)
        )

        agent = TwoStageEnvAgent(
            stage1_system_prompt=s1_prompt_text,
            stage2_system_prompt=s2_prompt_text,
            stage1_tools=stage1_tools,
            stage2_tools=stage2_tools,
            llm_server=llm_server,
            sandbox=sandbox,
            stage1_max_iterations=self.max_iterations,
            stage2_max_iterations=self.stage2_max_iterations,
        )

        stage1_user_prompt = (
            f"Install the dependencies for '{repo}' (language: {language}) at {self.work_dir}. "
            "Call only ONE tool per turn. "
            "When installation is verified, stop calling tools and output <install_script>."
        )
        stage2_user_prompt = (
            f"The environment for '{repo}' is already set up at {self.work_dir}. "
            "Discover the test runner and verify tests execute. "
            "Call only ONE tool per turn. "
            "When confirmed, stop calling tools and output <test_script>."
        )

        return agent.run(
            stage1_prompt=stage1_user_prompt,
            stage2_prompt=stage2_user_prompt,
        ).to_dict()

    # ── Sandbox helpers ───────────────────────────────────────────────

    def _init_sandbox(self, repo: str, image_name: str) -> SandboxK8s:
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
            scripts=self._SANDBOX_SCRIPTS,
            run_timeout=self.run_timeout,
        )

    def _setup_workdir(self, sandbox: SandboxK8s, reformat_path: str) -> None:
        sandbox.run_command(f"mkdir -p {self.work_dir}")
        sandbox.run_command(f"cp -r {reformat_path}/. {self.work_dir}/")
        sandbox.run_command('echo "conda activate base" >> /root/.bashrc || true')
        sandbox.run_command(f'echo "cd {self.work_dir}" >> /root/.bashrc || true')

    def _build_pod_name(self, repo: str) -> str:
        safe = repo.replace(".", "_").replace("__", "-").replace("_", "-").lower()
        suffix = random.randint(1000, 9999)
        pod_name = f"{self.pod_prefix}-{safe}-{suffix}"
        if len(pod_name) > 48:
            pod_name = f"{pod_name[:44]}-{suffix}"
        return pod_name

    # ── Output helpers ────────────────────────────────────────────────

    def _save_result(self, output_path: str, result: Dict[str, Any]) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
