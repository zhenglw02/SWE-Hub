"""Env-agent pipeline entry point.

Usage examples:
  # Run the full pipeline
  python -m env_agent.main --input repos.jsonl --output-root ./output

  # Skip repos that already have output files
  python -m env_agent.main --input repos.jsonl --output-root ./output --skip-existing

  # Use a specific LLM model and token
  python -m env_agent.main \\
      --input repos.jsonl \\
      --llm-model deepseek-v3.2 \\
      --llm-auth-token $QIANFAN_BEARER_TOKEN

Input JSONL format (one repo per line):
  {
    "repo":         "owner__repo__commit",   // used as unique identifier
    "repo_name":    "owner__repo__commit",   // same as repo (safe folder name)
    "image_name":   "registry.../swesmith.x86_64:latest",
    "reformat_path": "/path/on/cfs/to/source"
  }

Output: one JSON file per repo under <output-root>/step_1_env_setup/<repo>.json
  {
    "status":         "success | max_iteration | tool_stop | error",
    "install_script": "#!/bin/bash ...",
    "test_script":    "#!/bin/bash ...",
    "summary":        "...",
    "messages":       [...],   // full conversation history
    "error":          null     // error message if status != success
  }
"""

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

# Ensure both the pipeline root and project root are on sys.path so that
# `import env_agent` and `import code_data_agent` both resolve correctly.
_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _SCRIPT_DIR.parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]
for _p in (str(_PIPELINE_ROOT), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from env_agent.pipeline.context import PipelineContext
from env_agent.pipeline.steps.env_setup import EnvSetupStep


# ---------------------------------------------------------------------------
# Default environment variables injected into every K8s pod
# ---------------------------------------------------------------------------
def _default_env() -> dict:
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """parse args"""
    parser = argparse.ArgumentParser(
        description="env_agent — automated environment setup pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # I/O
    parser.add_argument("--input", "-i", required=True, help="Input JSONL path")
    parser.add_argument(
        "--output-root",
        default=os.path.join(str(_SCRIPT_DIR), "output"),
        help="Root directory for per-repo output JSON files",
    )

    # Flow control
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip repos that already have an output JSON file",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing remaining repos after a per-repo error",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum agent iterations for Stage 1 / one-stage (default: 100)",
    )
    parser.add_argument(
        "--stage2-max-iterations",
        type=int,
        default=60,
        help="Maximum agent iterations for Stage 2 (JS/TS two-stage only, default: 60)",
    )

    # K8s / sandbox
    parser.add_argument("--kubeconfig", default="", help="Path to kubeconfig file")
    parser.add_argument("--namespace", default="data-synthesis", help="K8s namespace")
    parser.add_argument(
        "--pod-prefix", default="code-data-env-agent", help="Pod name prefix"
    )
    parser.add_argument("--cpu-request", default="2", help="Pod CPU request")
    parser.add_argument("--memory-request", default="5Gi", help="Pod memory request")
    parser.add_argument(
        "--run-timeout", type=int, default=1800, help="Sandbox command timeout (seconds)"
    )

    # LLM
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("LLM_BASE_URL", ""),
        help="LLM API base URL (or set LLM_BASE_URL env var)",
    )
    parser.add_argument(
        "--llm-model",
        default="deepseek-v3.2",
        help="Model name",
    )
    parser.add_argument(
        "--llm-auth-token",
        default=os.environ.get("QIANFAN_BEARER_TOKEN", ""),
        help="Bearer token for LLM API (or set QIANFAN_BEARER_TOKEN env var)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------
def run_pipeline(
    input_path: str,
    output_root: str,
    skip_existing: bool,
    continue_on_error: bool,
    max_iterations: int,
    stage2_max_iterations: int,
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
    """run pipeline"""
    context = PipelineContext(
        input_path=input_path,
        output_root=output_root,
    )
    context.ensure_directories()
    context.load_input_jsonl()
    context.log_progress("Pipeline", f"Loaded {len(context.meta_list)} repos from {input_path}")

    if not llm_base_url:
        raise ValueError(
            "--llm-base-url is required (or set LLM_BASE_URL)"
        )
    if not llm_auth_token:
        raise ValueError(
            "--llm-auth-token is required (or set QIANFAN_BEARER_TOKEN)"
        )

    step = EnvSetupStep(
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
        max_iterations=max_iterations,
        stage2_max_iterations=stage2_max_iterations,
        continue_on_error=continue_on_error,
        skip_existing=skip_existing,
    )
    step.run(context)

    if context.errors:
        context.log_progress(
            "Pipeline",
            f"Finished with {len(context.errors)} error(s): {context.errors}",
        )
        return False

    context.log_progress("Pipeline", "All repos processed successfully.")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """main"""
    args = parse_args()
    setup_logging(args.log_level)

    if not os.path.exists(args.input):
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    try:
        success = run_pipeline(
            input_path=args.input,
            output_root=args.output_root,
            skip_existing=args.skip_existing,
            continue_on_error=args.continue_on_error,
            max_iterations=args.max_iterations,
            stage2_max_iterations=args.stage2_max_iterations,
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

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
