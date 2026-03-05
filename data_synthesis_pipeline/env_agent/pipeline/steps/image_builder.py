"""Image builder step: takes install_script from step-1 output and builds Docker images.

For each repo this step:
  1. Reads the per-repo JSON produced by EnvSetupStep (contains install_script / test_script).
  2. Starts a local Docker container from a configurable base image.
  3. Copies the source code (reformat_path) into /testbed inside the container.
  4. Executes the install_script with a configurable timeout.
  5. On success, commits the container as a new Docker image.
  6. Saves an updated JSON config (adds installed_image_name / install_success fields).
  7. Writes a __SUCCESS__ marker file to allow resume / skip logic.

Requires: pip install docker
"""

import io
import json
import os
import tarfile
from multiprocessing.pool import ThreadPool
from pathlib import Path
from typing import Any, Dict, List, Optional

from env_agent.pipeline.context import PipelineContext


class ImageBuilderStep:
    """Builds a Docker image per repo using the install_script from step 1.

    Parallelism is controlled by `num_workers` (default 1 — local Docker may
    not handle many concurrent builds well on a single machine).
    """

    def __init__(
        self,
        base_image: str,
        output_image_tag: str = "installed",
        output_image_prefix: str = "",
        work_dir: str = "/testbed",
        install_timeout: int = 3600,
        num_workers: int = 1,
        skip_existing: bool = True,
        continue_on_error: bool = False,
    ) -> None:
        """
        Args:
            base_image: Docker image to start from (e.g. swesmith.x86_64:latest).
            output_image_tag: Tag applied to the committed image (default "installed").
            output_image_prefix: Optional registry prefix prepended to the image name
                                  (e.g. "iregistry.example.com/team/").
            work_dir: Path inside the container where source code lives (/testbed).
            install_timeout: Seconds before the install_script is killed.
            num_workers: Number of parallel build workers.
            skip_existing: Skip repos that already have a __SUCCESS__ marker.
            continue_on_error: Keep going after per-repo failures.
        """
        self.base_image = base_image
        self.output_image_tag = output_image_tag
        self.output_image_prefix = output_image_prefix.rstrip("/")
        self.work_dir = work_dir
        self.install_timeout = install_timeout
        self.num_workers = num_workers
        self.skip_existing = skip_existing
        self.continue_on_error = continue_on_error

    # ── Public interface ──────────────────────────────────────────────

    def run(self, context: PipelineContext) -> None:
        """Build Docker images for all repos in context.meta_list.

        Reads install_script / test_script from the step-1 output JSON files
        (under context.get_env_setup_output_dir()), then builds images and
        writes updated JSONs to context.get_image_build_output_dir().
        """
        import docker  # local import — only needed at runtime

        step1_dir = context.get_env_setup_output_dir()
        output_dir = context.get_image_build_output_dir()
        os.makedirs(output_dir, exist_ok=True)

        # Collect tasks from step-1 output JSON files
        tasks: List[Dict[str, Any]] = []
        for meta in context.meta_list:
            repo = meta.get("repo") or meta.get("repo_name")
            if not repo:
                continue
            step1_path = context.get_env_setup_output_path(repo)
            if not os.path.exists(step1_path):
                context.add_error(
                    f"[ImageBuilder] step-1 output not found for {repo}: {step1_path}"
                )
                continue
            with open(step1_path, encoding="utf-8") as f:
                step1_data = json.load(f)

            out_path = context.get_image_build_output_path(repo)
            tasks.append(
                {
                    "repo": repo,
                    "step1_data": step1_data,
                    "output_path": out_path,
                }
            )

        context.log_progress("ImageBuilder", f"Building images for {len(tasks)} repos")

        client = docker.from_env(timeout=self.install_timeout + 120)

        def build_one(task: Dict[str, Any]) -> None:
            repo = task["repo"]
            out_path = task["output_path"]
            success_marker = out_path + "__SUCCESS__"

            if self.skip_existing and os.path.exists(success_marker):
                context.log_progress("ImageBuilder", f"Skipping {repo} (already built)")
                return

            context.log_progress("ImageBuilder", f"Building {repo}...")
            try:
                result = self._build_single(client, repo, task["step1_data"])
                _save_json(out_path, result)
                if result.get("install_success"):
                    Path(success_marker).write_text(result.get("installed_image_name", ""))
                    context.log_progress(
                        "ImageBuilder",
                        f"  OK  {repo} -> {result.get('installed_image_name')}",
                    )
                else:
                    context.log_progress(
                        "ImageBuilder",
                        f"  FAIL {repo}: {result.get('install_error')}",
                    )
            except Exception as exc:
                context.add_error(f"ImageBuilder failed for {repo}: {exc}")
                if not self.continue_on_error:
                    raise

        if self.num_workers > 1:
            with ThreadPool(self.num_workers) as pool:
                pool.map(build_one, tasks)
        else:
            for task in tasks:
                build_one(task)

    # ── Per-repo build ────────────────────────────────────────────────

    def _build_single(
        self, client, repo: str, step1_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run install_script in a fresh container and commit the result."""
        install_script = step1_data.get("install_script") or ""
        test_script = step1_data.get("test_script") or ""
        reformat_path = step1_data.get("reformat_path") or ""

        result = dict(step1_data)   # carry all existing fields forward
        result["install_success"] = False
        result["install_error"] = None
        result["installed_image_name"] = None

        if not install_script:
            result["install_error"] = "No install_script available (step-1 may have failed)"
            return result

        if not reformat_path or not os.path.exists(reformat_path):
            result["install_error"] = f"reformat_path not found: {reformat_path}"
            return result

        # Derive the target image name
        installed_image_name = self._make_image_name(repo, step1_data)

        # Proxy settings injected into the container (read from PIPELINE_PROXY env var)
        env_vars: Dict[str, str] = {}
        proxy = os.environ.get("PIPELINE_PROXY", "")
        if proxy:
            env_vars = {
                "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy,
                "http_proxy": proxy, "https_proxy": proxy,
                "ALL_PROXY": proxy,
            }

        container = None
        log_lines: List[str] = []

        try:
            # 1. Start fresh container from base image
            container = client.containers.run(
                image=self.base_image,
                command="sleep infinity",
                detach=True,
                tty=True,
                working_dir=self.work_dir,
                environment=env_vars,
            )

            # 2. Copy source code into /testbed
            tar_buf = io.BytesIO()
            with tarfile.open(fileobj=tar_buf, mode="w") as tar:
                tar.add(reformat_path, arcname=".")
            tar_buf.seek(0)
            container.put_archive(path=self.work_dir, data=tar_buf)

            # 3. Run install_script
            cmd = [
                "timeout", str(self.install_timeout),
                "/bin/bash", "-ec", install_script,
            ]
            exit_code, output = container.exec_run(cmd=cmd)
            log_text = output.decode("utf-8", errors="replace") if output else ""
            log_lines = log_text.splitlines()

            if exit_code != 0:
                tail = "\n".join(log_lines[-30:]) if log_lines else "(no output)"
                result["install_error"] = (
                    f"install_script exited with code {exit_code}\n{tail}"
                )
                return result

            # 4. Commit the container as a new image
            repo_name, tag = _split_image_tag(installed_image_name)
            changes = [
                f"WORKDIR {self.work_dir}",
                f'ENV PATH={self.work_dir}/node_modules/.bin:$PATH',
                'CMD ["/bin/bash"]',
            ]
            new_image = container.commit(
                repository=repo_name,
                tag=tag,
                changes=changes,
            )

            result["install_success"] = True
            result["installed_image_name"] = installed_image_name
            result["built_image"] = installed_image_name
            result["install_log_tail"] = "\n".join(log_lines[-20:])

        finally:
            if container:
                try:
                    container.stop(timeout=5)
                    container.remove()
                except Exception:
                    pass

        return result

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_image_name(self, repo: str, step1_data: Dict[str, Any]) -> str:
        """Construct the output image name for this repo."""
        # Prefer the image_name field from the original meta (without tag)
        base_name = step1_data.get("image_name") or repo.replace("__", "/").lower()
        # Strip any existing tag
        if ":" in base_name.split("/")[-1]:
            base_name = base_name.rsplit(":", 1)[0]
        if self.output_image_prefix:
            # Replace the registry portion if it already has one
            parts = base_name.split("/")
            # Assume first component is registry if it contains a dot or colon
            if "." in parts[0] or ":" in parts[0]:
                base_name = "/".join([self.output_image_prefix] + parts[1:])
            else:
                base_name = f"{self.output_image_prefix}/{base_name}"
        return f"{base_name}:{self.output_image_tag}"


# ── Module-level helpers ──────────────────────────────────────────────────────

def _save_json(path: str, data: Dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _split_image_tag(full_name: str):
    """Split 'registry/repo:tag' into ('registry/repo', 'tag')."""
    if ":" in full_name.split("/")[-1]:
        repo, tag = full_name.rsplit(":", 1)
        return repo, tag
    return full_name, "latest"
