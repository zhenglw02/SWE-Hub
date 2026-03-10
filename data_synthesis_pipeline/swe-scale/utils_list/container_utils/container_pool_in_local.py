import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import shlex
import uuid
import queue
import subprocess
from typing import *
from tqdm import tqdm
from contextlib import contextmanager
from utils_list.container_utils.container_pool import ContainerPool, ExecResult


class LocalContainerPool(ContainerPool):
    """
    预创建 N 个空转容器（tail -f /dev/null），通过 lease() 借出容器名，执行 docker exec。
    用完归还，__exit__ 时统一 rm -f。
    """
    def __init__(self, image: str, workdir: str = "/testbed", size: int = 4, bin_cmd: Optional[str] = None):
        self.image = image
        self.workdir = workdir
        self.size = size
        self.bin = bin_cmd or os.environ.get("CONTAINER_BIN", "docker")
        self._names = []
        self._q: "queue.LifoQueue[str]" = queue.LifoQueue()

    def __enter__(self) -> "ContainerPool":  # type: ignore[override]
        for _ in tqdm(range(self.size), ncols=70, desc="Preparing Pods"):
            name = f"testbed-{uuid.uuid4().hex[:16]}"
            # 创建 + 启动长驻容器
            subprocess.run(
                [self.bin, "create", "--name", name, "-w", self.workdir, "-m", "5g", self.image, "tail", "-f", "/dev/null"],
                check=True, 
                # stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.run([self.bin, "start", name], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._names.append(name)
            self._q.put(name)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        # 清理所有容器
        for n in self._names:
            subprocess.run([self.bin, "rm", "-f", n],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @contextmanager
    def lease(self):
        """借一个可用容器名，用完自动归还。"""
        name = self._q.get()
        try:
            yield name
        finally:
            self._q.put(name)

    def exec_script(self, container_name: str, script: str, capture: bool = True, timeout: int = 60) -> ExecResult:
        """
        sh-only 环境的 exec：
        - 确保容器在运行
        - 确保 workdir 存在
        - 用 sh -s -- 执行；失败时把输出（含错误）合并到异常信息
        """
        bin_ = self.bin
        workdir = self.workdir

        # 1) 容器在运行？
        insp = subprocess.run([bin_, "inspect", "-f", "{{.State.Running}}", container_name], text=True, capture_output=True)
        if insp.returncode != 0:
            raise RuntimeError(f"Container '{container_name}' not found. stderr:\n{insp.stderr}")
        if insp.stdout.strip().lower() != "true":
            start = subprocess.run([bin_, "start", container_name], text=True, capture_output=True)
            if start.returncode != 0:
                raise RuntimeError(f"Failed to start '{container_name}'. stderr:\n{start.stderr}")

        # 2) workdir 必须存在
        mk = subprocess.run([bin_, "exec", container_name, "sh", "-lc", f"mkdir -p {shlex.quote(workdir)}"], text=True, capture_output=True)
        if mk.returncode != 0:
            raise RuntimeError(f"Failed to ensure workdir '{workdir}'. stderr:\n{mk.stderr}")

        # 3) 包一层：在脚本里 cd，再执行传入脚本
        wrapped = f"set -eu\ncd {shlex.quote(workdir)}\n{script}"
        cmd = [bin_, "exec", "-i", container_name, "sh", "-s", "--"]

        if capture:
            # 合并 stderr 到 stdout，保持日志顺序
            res = subprocess.run(
                cmd,
                input=wrapped,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并
                check=False,
            )
            if res.returncode != 0:
                raise RuntimeError(
                    f"docker exec failed (code={res.returncode}) in container '{container_name}'.\nOUTPUT:\n{res.stdout}"
                )
            return ExecResult(stdout=res.stdout or "", stderr="", returncode=0)
        else:
            # 不捕获输出：直接把容器的输出打到当前进程的 stdout，stderr 同样并到 stdout 方便人眼查看
            res = subprocess.run(
                cmd,
                input=wrapped,
                text=True,
                stderr=subprocess.STDOUT,  # 合并
                check=False,
            )
            if res.returncode != 0:
                # 输出已打印到控制台，这里提示查看上面的控制台输出
                raise RuntimeError(
                    f"docker exec failed (code={res.returncode}) in container '{container_name}'.\nSee console output above."
                )
            return ExecResult(stdout="", stderr="", returncode=0)
