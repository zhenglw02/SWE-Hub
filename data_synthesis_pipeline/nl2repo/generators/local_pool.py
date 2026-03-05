"""Local Docker container pool for parallel execution.

Provides a pool of pre-created Docker containers for efficient
parallel script execution.
"""

import os
import queue
import shlex
import subprocess
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from tqdm import tqdm


@dataclass
class ExecResult:
    """Result of command execution in container."""
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class ContainerPool(ABC):
    """Abstract base for container pools.
    
    Provides unified interface for local Docker and remote
    Kubernetes container pools.
    """
    
    image: str
    workdir: str
    size: int
    
    def __init__(self, image: str, workdir: str = "/testbed", size: int = 4):
        """Initialize container pool.
        
        Args:
            image: Docker image name
            workdir: Working directory in containers
            size: Number of containers in pool
        """
        self.image = image
        self.workdir = workdir
        self.size = size
    
    @abstractmethod
    def __enter__(self) -> "ContainerPool":
        """Enter context manager."""
        ...
    
    @abstractmethod
    def __exit__(self, exc_type, exc, tb) -> None:
        """Exit context manager and cleanup."""
        ...
    
    @contextmanager
    @abstractmethod
    def lease(self) -> Iterator[str]:
        """Lease a container from pool.
        
        Yields container name and returns it to pool on exit.
        """
        ...
    
    @abstractmethod
    def exec_script(
        self,
        container_name: str,
        script: str,
        capture: bool = True,
        timeout: int = 60,
    ) -> ExecResult:
        """Execute script in container.
        
        Args:
            container_name: Name of container to execute in
            script: Shell script content
            capture: Whether to capture output
            timeout: Execution timeout in seconds
            
        Returns:
            ExecResult with output and return code
        """
        ...


class LocalContainerPool(ContainerPool):
    """Docker-based container pool for local execution.
    
    Pre-creates N containers running 'tail -f /dev/null' and
    provides lease/return semantics for parallel usage.
    """
    
    def __init__(
        self,
        image: str,
        workdir: str = "/testbed",
        size: int = 4,
        bin_cmd: Optional[str] = None,
        memory_limit: str = "5g",
    ):
        """Initialize local container pool.
        
        Args:
            image: Docker image name
            workdir: Working directory in containers
            size: Number of containers to create
            bin_cmd: Docker binary command (default: docker)
            memory_limit: Memory limit per container
        """
        super().__init__(image, workdir, size)
        self.bin = bin_cmd or os.environ.get("CONTAINER_BIN", "docker")
        self.memory_limit = memory_limit
        self._names: list[str] = []
        self._q: queue.LifoQueue[str] = queue.LifoQueue()
    
    def __enter__(self) -> "ContainerPool":
        """Create and start containers."""
        for _ in tqdm(range(self.size), ncols=70, desc="Preparing containers"):
            name = f"testbed-{uuid.uuid4().hex[:16]}"
            
            # Create container
            subprocess.run(
                [
                    self.bin, "create",
                    "--name", name,
                    "-w", self.workdir,
                    "-m", self.memory_limit,
                    self.image,
                    "tail", "-f", "/dev/null",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # Start container
            subprocess.run(
                [self.bin, "start", name],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            self._names.append(name)
            self._q.put(name)
        
        return self
    
    def __exit__(self, exc_type, exc, tb) -> None:
        """Stop and remove all containers."""
        for name in self._names:
            subprocess.run(
                [self.bin, "rm", "-f", name],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    
    @contextmanager
    def lease(self) -> Iterator[str]:
        """Lease a container from pool.
        
        Yields:
            Container name
        """
        name = self._q.get()
        try:
            yield name
        finally:
            self._q.put(name)
    
    def exec_script(
        self,
        container_name: str,
        script: str,
        capture: bool = True,
        timeout: int = 60,
    ) -> ExecResult:
        """Execute shell script in container.
        
        Args:
            container_name: Target container name
            script: Shell script to execute
            capture: Whether to capture output
            timeout: Execution timeout
            
        Returns:
            ExecResult with output
            
        Raises:
            RuntimeError: If container not found or execution fails
        """
        # Verify container is running
        insp = subprocess.run(
            [self.bin, "inspect", "-f", "{{.State.Running}}", container_name],
            text=True,
            capture_output=True,
        )
        
        if insp.returncode != 0:
            raise RuntimeError(
                f"Container '{container_name}' not found.\nstderr: {insp.stderr}"
            )
        
        if insp.stdout.strip().lower() != "true":
            # Try to start container
            start = subprocess.run(
                [self.bin, "start", container_name],
                text=True,
                capture_output=True,
            )
            if start.returncode != 0:
                raise RuntimeError(
                    f"Failed to start '{container_name}'.\nstderr: {start.stderr}"
                )
        
        # Ensure workdir exists
        mk = subprocess.run(
            [
                self.bin, "exec", container_name,
                "sh", "-lc", f"mkdir -p {shlex.quote(self.workdir)}",
            ],
            text=True,
            capture_output=True,
        )
        if mk.returncode != 0:
            raise RuntimeError(
                f"Failed to create workdir '{self.workdir}'.\nstderr: {mk.stderr}"
            )
        
        # Wrap script with cd to workdir
        wrapped = f"set -eu\ncd {shlex.quote(self.workdir)}\n{script}"
        cmd = [self.bin, "exec", "-i", container_name, "sh", "-s", "--"]
        
        if capture:
            res = subprocess.run(
                cmd,
                input=wrapped,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if res.returncode != 0:
                raise RuntimeError(
                    f"Execution failed (code={res.returncode}) in '{container_name}'.\n"
                    f"OUTPUT:\n{res.stdout}"
                )
            return ExecResult(stdout=res.stdout or "", stderr="", returncode=0)
        else:
            res = subprocess.run(
                cmd,
                input=wrapped,
                text=True,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if res.returncode != 0:
                raise RuntimeError(
                    f"Execution failed (code={res.returncode}) in '{container_name}'.\n"
                    "See console output above."
                )
            return ExecResult(stdout="", stderr="", returncode=0)