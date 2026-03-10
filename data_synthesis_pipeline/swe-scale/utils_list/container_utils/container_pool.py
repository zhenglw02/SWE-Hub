from __future__ import annotations
from dataclasses import dataclass
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator

# ------------------------------
# Common result shape (subprocess-like)
# ------------------------------
@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

# ------------------------------
# Abstract base container pool
# ------------------------------
class ContainerPool(ABC):
    """
    ABC for container pools (local Docker or remote KODO).

    Unifies the minimal surface used by call sites:
      - context manager for lifecycle (pre-spawn & cleanup)
      - lease() to get a running container/pod name (str)
      - exec_script(name, script, capture=True) -> ExecResult
    """

    image: str
    workdir: str
    size: int

    def __init__(self, image: str, workdir: str = "/testbed", size: int = 4):
        self.image = image
        self.workdir = workdir
        self.size = size

    # 直接把魔术方法设为抽象方法，让子类实现
    @abstractmethod
    def __enter__(self) -> "ContainerPool":
        ...

    @abstractmethod
    def __exit__(self, exc_type, exc, tb) -> None:
        ...

    @contextmanager
    @abstractmethod
    def lease(self) -> Iterator[str]:
        """Yield a container/pod name; auto-return on exit."""
        ...

    @abstractmethod
    def exec_script(self, container_name: str, script: str, capture: bool = True, timeout: int = 60) -> ExecResult:
        ...
