"""Sandbox local implementation"""

import subprocess
from typing import Dict, Iterable, List, Optional

from code_data_agent.model.sandbox import SandboxRunResult, SandboxScript
from code_data_agent.sandbox.sandbox_base import SandboxBase


class SandboxLocal(SandboxBase):
    """Simple sandbox that launches tools directly via subprocess."""

    def __init__(self, python_bin: str, scripts: Iterable[SandboxScript]):
        """
        Args:
            python_bin: The path to the Python interpreter to use.
            scripts: A collection of scripts recognized by the sandbox.
        """
        self._python_bin = python_bin
        self._scripts = scripts

    def run_command(self, command: str, args: Optional[dict]) -> SandboxRunResult:
        """Execute a command directly and return its result."""
        cmd_parts = [command]
        cmd_parts.extend(self._format_args(args))
        return self._execute(cmd_parts)

    def run_script(
        self, script: SandboxScript, args: Optional[dict]
    ) -> SandboxRunResult:
        """Execute a registered script inside the sandbox."""
        if script not in self._scripts:
            return SandboxRunResult(
                exit_code=-1, output=f"script '{script.to_dict()}' not found"
            )

        cmd_parts = [self._python_bin, script.path]
        cmd_parts.extend(self._format_args(args))
        return self._execute(cmd_parts)

    def _execute(self, cmd_parts: List[str]) -> SandboxRunResult:
        """_execute."""
        try:
            result = subprocess.run(cmd_parts, capture_output=True, text=True)
            output = result.stdout or ""
            error = result.stderr or ""
            combined = output.strip()
            if error.strip():
                combined = f"{combined}\n{error.strip()}".strip()
            return SandboxRunResult(exit_code=result.returncode, output=combined)
        except FileNotFoundError as exc:
            return SandboxRunResult(exit_code=-1, output=str(exc))

    def close(self) -> None:
        """no ops for local sandbox."""
        pass
