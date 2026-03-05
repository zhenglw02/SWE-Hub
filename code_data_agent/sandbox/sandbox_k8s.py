"""Kubernetes-based sandbox implementation backed by kodo ContainerRunner."""

import base64
import os
import posixpath
import shlex
import threading
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from code_data_agent.model.sandbox import SandboxRunResult, SandboxScript
from code_data_agent.sandbox.sandbox_base import SandboxBase

try:
    from kodo.core import ContainerRunner
except ImportError:  # pragma: no cover - runtime guard
    ContainerRunner = None  # type: ignore


class SandboxK8s(SandboxBase):
    """Execute tools inside an existing Kubernetes pod via kodo."""

    def __init__(
        self,
        pod_name: str,
        namespace: str = "default",
        kubeconfig_path: Optional[str] = None,
        image: Optional[str] = None,
        enveriment: Optional[Dict[str, str]] = None,
        cpu_request: Optional[str] = None,
        memory_request: Optional[str] = None,
        workdir: str = "/workspace/scripts",
        conda_dir: str = "",
        conda_env: str = "",
        python_bin: str = "/opt/miniconda3/envs/testbed/bin/python",
        scripts: Iterable[SandboxScript] = [],
        run_timeout: Optional[int] = None,
        max_life_time: Optional[int] = None,
    ):
        """Init a Kubernetes sandbox with optional lifetime control."""
        if ContainerRunner is None:
            raise ImportError("kodo is required to use SandboxK8s")
        if not image:
            raise ValueError("image is required to launch a Kubernetes sandbox pod")

        self.runner = ContainerRunner(
            backend="kubernetes",
            namespace=namespace,
            kubeconfig_path=kubeconfig_path,
        )
        self.image = image
        self.environment = dict(enveriment or {})
        self.pod_name = pod_name
        self.workdir = workdir.rstrip("/") or "/workspace/scripts"
        self.python_bin = python_bin
        self.namespace = namespace
        self.cpu_request = cpu_request
        self.memory_request = memory_request
        self.pod = None
        self._closed = False
        self._conda_dir = conda_dir
        self._conda_env = conda_env
        self.run_timeout = run_timeout
        self.max_life_time = max_life_time
        self._life_timer: Optional[threading.Timer] = None

        self._script_paths: Dict[str, str] = {}

        self._recreate_pod()

        scripts = list(scripts or [])
        if scripts:
            self._prepare_remote_dir()
            for script in scripts:
                remote_path = self._copy_script_to_pod(script)
                self._script_paths[script.name] = remote_path

    def run_command(self, command: str, args: dict = None) -> SandboxRunResult:
        """Execute a raw command inside the pod."""
        if not self.pod:
            return SandboxRunResult(exit_code=-1, output="pod not ready or has been released")

        commands = []
        if self._conda_dir and self._conda_env:
            commands.append(f". {self._conda_dir}/etc/profile.d/conda.sh")
            commands.append(f"conda activate {self._conda_env}")

        cmd_parts = [command]
        cmd_parts.extend(self._format_args(args))

        commands.append(" ".join(part for part in cmd_parts))
        return self._exec_in_pod(commands)

    def run_script(
        self, script: SandboxScript, args: Optional[dict]
    ) -> SandboxRunResult:
        """Execute a registered script by name."""
        if not self.pod:
            return SandboxRunResult(exit_code=-1, output="pod not ready or has been released")

        script_path = self._script_paths.get(script.name)
        if not script_path:
            return SandboxRunResult(
                exit_code=-1,
                output=f"script '{script.name}' not found in pod",
            )

        commands = []
        if self._conda_dir and self._conda_env:
            commands.append(f". {self._conda_dir}/etc/profile.d/conda.sh")
            commands.append(f"conda activate {self._conda_env}")

        cmd_parts = [self.python_bin, script_path]
        cmd_parts.extend(self._format_args(args))
        commands.append(" ".join(shlex.quote(part) for part in cmd_parts))
        return self._exec_in_pod(commands)

    def _prepare_remote_dir(self) -> None:
        """Ensure remote work directory exists inside the pod."""
        self._runner_exec(f"mkdir -p {shlex.quote(self.workdir)}")

    def _copy_script_to_pod(self, script: SandboxScript) -> str:
        """Copy a local script to the pod and return remote path."""
        remote_filename = os.path.basename(script.path) or script.name
        remote_path = posixpath.join(self.workdir, remote_filename)
        with open(script.path, "rb") as fp:
            encoded = base64.b64encode(fp.read()).decode("utf-8")
        dir_path = posixpath.dirname(remote_path)
        copy_cmd = (
            f"mkdir -p {shlex.quote(dir_path)} && "
            f"echo '{encoded}' | base64 -d > {shlex.quote(remote_path)}"
        )
        self._runner_exec(copy_cmd)
        return remote_path

    def _exec_in_pod(self, commands: List[str]) -> SandboxRunResult:
        """Run composed shell commands inside pod and normalize result."""
        command = " && ".join(commands)
        print(f"command: {command}")
        raw_result = self._runner_exec(command)

        exit_code, output = self._normalize_result(raw_result)
        return SandboxRunResult(exit_code=exit_code, output=output)

    def _runner_exec(self, command: str):
        """Execute a command using ContainerRunner with timeout logic applied."""
        wrapped = self._apply_timeout(command)
        return self.runner.execute_command(self._pod_ref, wrapped)

    def _apply_timeout(self, command: str) -> str:
        """Wrap command with timeout if run_timeout is set."""
        if self.run_timeout and self.run_timeout > 0:
            seconds = max(int(self.run_timeout), 1)
            quoted = shlex.quote(command)
            return f"timeout -s KILL {seconds}s sh -c {quoted}"
        return command

    def _normalize_result(self, raw: Union[str, Tuple, Dict, None]) -> Tuple[int, str]:
        """Normalize ContainerRunner responses into exit_code/output pair."""
        exit_code = 0
        output = ""

        if isinstance(raw, tuple):
            if raw:
                output = str(raw[0]) if raw[0] is not None else ""
            if len(raw) > 1:
                try:
                    exit_code = int(raw[1])
                except (TypeError, ValueError):
                    exit_code = 1
        elif isinstance(raw, dict):
            exit_code = int(raw.get("exit_code", raw.get("returncode", 0)) or 0)
            output = str(
                raw.get("output", raw.get("stdout", raw.get("result", ""))) or ""
            )
        elif hasattr(raw, "exit_code"):
            exit_code = int(getattr(raw, "exit_code") or 0)
            output = str(getattr(raw, "output", "") or "")
        elif raw is not None:
            output = str(raw)

        return exit_code, output

    def _recreate_pod(self) -> None:
        """Recreate a pod by stopping old one and launching a new container."""
        self._cleanup_existing_pod()

        resources = self._build_resource_requests()
        env = self.environment.copy()
        if self.workdir:
            env["PYTHONPATH"] = f"{self.workdir}:$PYTHONPATH"

        base_command = "sleep infinity"
        if self.max_life_time and self.max_life_time > 0:
            base_command = f"sleep {self.max_life_time}"

        self.pod = self.runner.start_container(
            image=self.image,
            name=self.pod_name,
            command=base_command,
            environment=env or None,
            resources=resources,
        )
        self._start_life_timer()

    def _cleanup_existing_pod(self) -> None:
        """Stop an existing pod if present."""
        self._cancel_life_timer()
        try:
            self.runner.stop_container(self.pod_name)
        except Exception:
            pass
        finally:
            self.pod = None

    def _build_resource_requests(self) -> Optional[Dict[str, Any]]:
        """Build Kubernetes resource requests payload."""
        requests: Dict[str, str] = {}
        if self.cpu_request:
            requests["cpu"] = self.cpu_request
        if self.memory_request:
            requests["memory"] = self.memory_request
        if not requests:
            return None
        return {"requests": requests}

    @property
    def _pod_ref(self):
        """Return ContainerRunner reference for current pod."""
        if self.pod is not None:
            return self.pod
        return self.pod_name

    def close(self) -> None:
        """Stop pod and cancel timers."""
        if self._closed:
            return
        try:
            self._cancel_life_timer()
            if self.pod is not None:
                self.runner.stop_container(self.pod)
                self.pod = None
        finally:
            self._closed = True

    def _start_life_timer(self) -> None:
        """Start a background timer to enforce max_life_time."""
        self._cancel_life_timer()
        if not self.max_life_time or self.max_life_time <= 0:
            return
        self._life_timer = threading.Timer(self.max_life_time, self._handle_life_timeout)
        self._life_timer.daemon = True
        self._life_timer.start()

    def _cancel_life_timer(self) -> None:
        """Cancel the lifetime timer if one is running."""
        if self._life_timer is not None:
            self._life_timer.cancel()
            self._life_timer = None

    def _handle_life_timeout(self) -> None:
        """Handle lifetime timeout by stopping the pod."""
        try:
            self.runner.stop_container(self.pod_name)
        except Exception:
            pass
        finally:
            self.pod = None
            self._closed = True
