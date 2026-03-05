"""Coverage collection step - runs tests and collects coverage data."""

import os
from typing import Dict, List, Optional

from tqdm import tqdm

from nl2repo.config import get_settings
from nl2repo.config.defaults import COVERAGE_COMMAND_TEMPLATE
from nl2repo.pipeline.context import PipelineContext
from nl2repo.models.task import CoverageTask, CoverageResult


class CoverageStep:
    """Collects code coverage by running tests in containers.
    
    This step creates sandbox containers, runs pytest with coverage,
    and saves coverage reports for analysis.
    
    Supports three execution modes:
    1. Sequential (default) - simple but slow
    2. Serial execution via SandboxK8s
    3. Skip completed - resume from previous run
    """
    
    def __init__(
        self,
        num_runs: int = 10,
        timeout: Optional[int] = None,
        rcfile: Optional[str] = None,
        parallel_workers: int = 128,
    ):
        """Initialize coverage step.
        
        Args:
            num_runs: Number of coverage runs per repo
            timeout: Execution timeout in seconds
            rcfile: Path to coverage.ini config file
            parallel_workers: Number of parallel workers for execution
        """
        settings = get_settings()
        self.num_runs = num_runs
        self.timeout = timeout or settings.coverage_timeout
        self.rcfile = rcfile or settings.coverage_rcfile
        self.parallel_workers = parallel_workers
    
    def run(self, context: PipelineContext) -> None:
        """Execute coverage collection for all repos (sequential mode).
        
        For parallel execution, use run_parallel() instead.
        
        Args:
            context: Pipeline context with meta_list populated
        """
        context.log_progress("Coverage", f"Collecting coverage for {len(context.meta_list)} repos")
        
        tasks = self._build_tasks(context)
        context.log_progress("Coverage", f"Created {len(tasks)} coverage tasks")
        
        # Sequential execution
        for task in tqdm(tasks, desc="Running coverage", ncols=70):
            try:
                result = self.run_single(task)
                if not result.success:
                    context.add_error(f"Coverage failed for {task.repo}:{task.index}")
            except Exception as e:
                context.add_error(f"Coverage error for {task.repo}:{task.index}: {e}")
    
    def run_parallel(self, context: PipelineContext) -> Dict[str, List[CoverageResult]]:
        """Execute coverage collection in serial mode.
        
        Args:
            context: Pipeline context with meta_list populated
            
        Returns:
            Empty dict (serial execution does not aggregate results here)
        """
        context.log_progress(
            "Coverage",
            f"Parallel mode disabled; running serially for {len(context.meta_list)} repos",
        )
        self.run(context)
        return {}
    
    def _build_tasks(self, context: PipelineContext) -> List[CoverageTask]:
        """Build task list from context."""
        tasks = []
        for meta in context.meta_list:
            for idx in range(self.num_runs):
                task = self._create_task(meta, idx, context)
                tasks.append(task)
        return tasks
    
    def _create_task(self, meta, idx: int, context: PipelineContext) -> CoverageTask:
        """Create a single coverage task."""
        output_dir = os.path.join(
            context.coverage_dir,
            meta.repo,
            f"ground_truth_{idx:04d}",
        )
        os.makedirs(output_dir, exist_ok=True)
        
        return CoverageTask(
            repo=meta.repo,
            image_name=meta.image_name,
            base_commit=meta.base_commit,
            output_dir=output_dir,
            index=idx,
        )
    
    def _is_completed(self, task: CoverageTask) -> bool:
        """Check if a task is already completed."""
        coverage_path = os.path.join(task.output_dir, "coverage.json")
        return os.path.exists(coverage_path)
    
    def _build_command(self, task: CoverageTask) -> str:
        """Build coverage command for a task."""
        coverage_path = os.path.join(task.output_dir, "coverage.json")
        xml_path = os.path.join(task.output_dir, "test_report.xml")
        log_path = os.path.join(task.output_dir, "test_report.log")
        
        return COVERAGE_COMMAND_TEMPLATE.format(
            rcfile=self.rcfile,
            xml_path=xml_path,
            log_path=log_path,
            json_path=coverage_path,
        )
    
    def run_single(self, task: CoverageTask) -> CoverageResult:
        """Run coverage for a single task (requires sandbox to be set up externally).
        
        This method checks if the task is already completed, and if not,
        creates a temporary sandbox for execution.
        
        Args:
            task: Coverage task definition
            
        Returns:
            CoverageResult with status
        """
        coverage_path = os.path.join(task.output_dir, "coverage.json")
        xml_path = os.path.join(task.output_dir, "test_report.xml")
        log_path = os.path.join(task.output_dir, "test_report.log")
        
        # Check if already completed
        if os.path.exists(coverage_path):
            return CoverageResult(
                task=task,
                success=True,
                coverage_path=coverage_path,
                xml_report_path=xml_path,
                log_path=log_path,
            )
        
        # Try to create sandbox and run
        try:
            from code_data_agent.sandbox.sandbox_k8s import SandboxK8s
            
            settings = get_settings()
            pod_name = f"cov-{task.repo_name}-{task.index:04d}"
            sandbox = SandboxK8s(
                pod_name=pod_name,
                namespace=settings.k8s_namespace,
                kubeconfig_path=settings.kubeconfig_path,
                image=task.image_name,
                enveriment=settings.get_container_environment(),
                cpu_request=settings.cpu_request,
                memory_request=settings.memory_request,
                workdir=settings.workdir,
                run_timeout=self.timeout,
            )
            try:
                return self.run_with_sandbox(task, sandbox)
            finally:
                sandbox.close()
                
        except ImportError as e:
            return CoverageResult(
                task=task,
                success=False,
                error_message=f"Sandbox not available: {e}.",
            )
        except Exception as e:
            return CoverageResult(
                task=task,
                success=False,
                error_message=str(e),
            )
    
    def run_with_sandbox(
        self,
        task: CoverageTask,
        sandbox,
    ) -> CoverageResult:
        """Run coverage using a sandbox instance.
        
        Args:
            task: Coverage task definition
            sandbox: SandboxK8s or compatible sandbox instance
            
        Returns:
            CoverageResult with status
        """
        coverage_path = os.path.join(task.output_dir, "coverage.json")
        xml_path = os.path.join(task.output_dir, "test_report.xml")
        log_path = os.path.join(task.output_dir, "test_report.log")
        
        # Check if already completed
        if os.path.exists(coverage_path):
            return CoverageResult(
                task=task,
                success=True,
                coverage_path=coverage_path,
                xml_report_path=xml_path,
                log_path=log_path,
            )
        
        # Build command
        command = self._build_command(task)
        
        try:
            result = sandbox.run_command(command)
            success = result.exit_code == 0
            
            return CoverageResult(
                task=task,
                success=success,
                coverage_path=coverage_path if success else None,
                xml_report_path=xml_path,
                log_path=log_path,
                error_message=None if success else result.output,
            )
        except Exception as e:
            return CoverageResult(
                task=task,
                success=False,
                error_message=str(e),
            )
