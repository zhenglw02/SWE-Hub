"""Bug agent pipeline entry point."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """setup logging"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _SCRIPT_DIR.parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]
for path in (str(_PIPELINE_ROOT), str(_PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from bug_agent.pipeline.context import PipelineContext
from bug_agent.pipeline.steps import PreprocessStep, BugIssueStep


def parse_args() -> argparse.Namespace:
    """parse_args."""
    parser = argparse.ArgumentParser(
        description="bug_agent - Preprocess + BugIssue Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preprocess only (write new jsonl)
  python -m bug_agent.main --steps preprocess --input input.jsonl --output output.jsonl

  # BugIssue only (read enriched jsonl)
  python -m bug_agent.main --steps bug_issue --input enriched.jsonl --output-root ./output

  # All steps
  python -m bug_agent.main --steps all --input input.jsonl --output output.jsonl
        """,
    )

    parser.add_argument("--input", "-i", required=True, help="Input JSONL path")
    parser.add_argument(
        "--output",
        "-o",
        default="",
        help="Output JSONL path (required for preprocess)",
    )
    parser.add_argument(
        "--output-root",
        default=os.path.join(str(_SCRIPT_DIR), "output"),
        help="Root directory for bug_issue outputs",
    )
    parser.add_argument(
        "--report-root",
        default=os.path.join(str(_SCRIPT_DIR), "reports"),
        help="Root directory for preprocess reports",
    )
    parser.add_argument(
        "--steps",
        default="all",
        help="Steps to run: preprocess,bug_issue,all",
    )

    # Preprocess options
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing preprocess outputs")
    parser.add_argument("--force-preprocess", action="store_true", help="Force preprocess even if outputs exist")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue on error")

    # Sandbox options
    parser.add_argument(
        "--kubeconfig",
        default="",
        help="Kubeconfig path",
    )
    parser.add_argument("--namespace", default="data-synthesis", help="K8s namespace")
    parser.add_argument("--pod-prefix", default="code-data-bug-agent", help="Pod name prefix")
    parser.add_argument("--cpu-request", default="2", help="CPU request")
    parser.add_argument("--memory-request", default="5Gi", help="Memory request")
    parser.add_argument("--run-timeout", type=int, default=1800, help="Sandbox timeout")

    # LLM options
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("LLM_BASE_URL", ""),
        help="LLM API base URL (or set LLM_BASE_URL env var)",
    )
    parser.add_argument("--llm-model", default="deepseek-v3.2", help="LLM model")
    parser.add_argument(
        "--llm-auth-token",
        default=os.environ.get("QIANFAN_BEARER_TOKEN", ""),
        help="LLM auth token (or env QIANFAN_BEARER_TOKEN)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    return parser.parse_args()


def get_steps_to_run(steps_arg: str) -> List[str]:
    """get_steps_to_run."""
    all_steps = ["preprocess", "bug_issue"]
    if steps_arg.lower() == "all":
        return all_steps
    requested = [s.strip().lower() for s in steps_arg.split(",") if s.strip()]
    return [s for s in requested if s in all_steps]


def run_pipeline(
    input_path: str,
    output_path: str,
    output_root: str,
    report_root: str,
    steps: List[str],
    skip_existing: bool,
    force_preprocess: bool,
    continue_on_error: bool,
    kubeconfig_path: str,
    namespace: str,
    pod_prefix: str,
    cpu_request: str,
    memory_request: str,
    run_timeout: int,
    llm_base_url: str,
    llm_model: str,
    llm_auth_token: str,
) -> bool:
    """run_pipeline."""
    context = PipelineContext(
        input_path=input_path,
        output_path=output_path or None,
        output_root=output_root,
        report_root=report_root,
    )
    context.ensure_directories()
    context.load_input_jsonl()

    if "preprocess" in steps:
        if not output_path:
            raise ValueError("--output is required when running preprocess")
        preprocess = PreprocessStep(
            kubeconfig_path=kubeconfig_path or None,
            namespace=namespace,
            pod_prefix=pod_prefix,
            cpu_request=cpu_request,
            memory_request=memory_request,
            run_timeout=run_timeout,
            env=_default_env(),
            skip_existing=(skip_existing and not force_preprocess),
            continue_on_error=continue_on_error,
        )
        preprocess.run(context)
        context.save_output_jsonl()

    if "bug_issue" in steps:
        if not llm_base_url:
            raise ValueError("--llm-base-url is required for bug_issue (or set LLM_BASE_URL)")
        if not llm_auth_token:
            raise ValueError("--llm-auth-token is required for bug_issue")
        bug_issue = BugIssueStep(
            kubeconfig_path=kubeconfig_path or None,
            namespace=namespace,
            pod_prefix=pod_prefix,
            cpu_request=cpu_request,
            memory_request=memory_request,
            run_timeout=run_timeout,
            env=_default_env(),
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_auth_token=llm_auth_token,
            continue_on_error=continue_on_error,
        )
        bug_issue.run(context)

    return True


def _default_env() -> dict:
    """_default_env."""
    env = {
        "PYTHONIOENCODING": "utf-8",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    proxy = os.environ.get("PIPELINE_PROXY", "")
    if proxy:
        env.update({
            "ALL_PROXY": proxy,
            "HTTP_PROXY": proxy,
            "HTTPS_PROXY": proxy,
            "http_proxy": proxy,
            "https_proxy": proxy,
        })
    return env


def main() -> None:
    """main."""
    args = parse_args()
    setup_logging(args.log_level)

    steps = get_steps_to_run(args.steps)
    if not steps:
        logger.error("No valid steps to run")
        sys.exit(1)

    if not os.path.exists(args.input):
        logger.error("Input not found: %s", args.input)
        sys.exit(1)

    try:
        run_pipeline(
            input_path=args.input,
            output_path=args.output,
            output_root=args.output_root,
            report_root=args.report_root,
            steps=steps,
            skip_existing=args.skip_existing,
            force_preprocess=args.force_preprocess,
            continue_on_error=args.continue_on_error,
            kubeconfig_path=args.kubeconfig,
            namespace=args.namespace,
            pod_prefix=args.pod_prefix,
            cpu_request=args.cpu_request,
            memory_request=args.memory_request,
            run_timeout=args.run_timeout,
            llm_base_url=args.llm_base_url,
            llm_model=args.llm_model,
            llm_auth_token=args.llm_auth_token,
        )
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
