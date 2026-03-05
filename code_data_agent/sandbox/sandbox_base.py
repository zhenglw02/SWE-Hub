"""Abstract interface for sandboxes that execute commands and scripts."""

import json
from abc import ABCMeta, abstractmethod
from typing import List, Optional

from code_data_agent.model.sandbox import SandboxScript, SandboxRunResult, ARG_COMMAND


class SandboxBase(metaclass=ABCMeta):
    """Common interface every sandbox backend must implement."""

    @abstractmethod
    def run_command(self, command: str, args: Optional[dict]) -> SandboxRunResult:
        """Execute a command directly and return its result."""

    @abstractmethod
    def run_script(self, script: SandboxScript, args: Optional[dict]) -> SandboxRunResult:
        """Execute a registered script inside the sandbox."""
    
    @abstractmethod
    def close(self):
        """Release any resources held by the sandbox."""

    def _format_args(self, args: Optional[dict]) -> List[str]:
        """Convert keyword args into CLI-style flag/value pairs."""
        if not args:
            return []

        formatted: List[str] = []
        if ARG_COMMAND in args:
            formatted.append(str(args[ARG_COMMAND]))

        for key, value in args.items():
            if key == ARG_COMMAND:
                continue
            if value is None:
                continue
            
            flag = f"--{key}"
            if isinstance(value, bool):
                if value:
                    formatted.append(flag)
                continue

            if isinstance(value, (list, dict)):
                formatted.extend([flag, json.dumps(value)])
            else:
                formatted.extend([flag, str(value)])
        return formatted
