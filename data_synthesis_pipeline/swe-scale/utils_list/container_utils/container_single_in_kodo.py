# container_single.py
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import time
import shlex
import uuid
from contextlib import contextmanager
from typing import Optional, Dict, Any

# KODO runtime
from kodo.core import ContainerRunner
from utils_list.container_utils.container_pool import ContainerPool, ExecResult


class KodoSingleUsePool(ContainerPool):
    """
    单实例容器池（语义：每次 lease() 启动一个容器，用完立刻销毁）。
    - 保持 ContainerPool 的外部接口不变：__enter__/__exit__/lease/exec_script
    - 返回 ExecResult(stdout, stderr, returncode) 不变
    - run_patch_in_container_pool 内部的调用逻辑无需改（with pool.lease() as name）
    """

    def __init__(
        self,
        image: str,
        workdir: str = "/testbed",
        *,
        namespace: Optional[str] = None,
        kubeconfig_path: Optional[str] = None,
        node_selector: Optional[Dict[str, str]] = None,
        environment: Optional[Dict[str, str]] = None,
        resources: Optional[Dict[str, str]] = None,
        name_prefix: str = "zyc-swe-smith-pytest",
        pod_start_timeout: int = 120
    ):
        self.image = image
        self.workdir = workdir
        self.namespace = namespace or os.getenv("LLM_NAMESPACE", 'data-synthesis')
        self.kubeconfig_path = kubeconfig_path or os.getenv("KUBECONFIG")
        self.node_selector = node_selector
        self.environment = environment or {
            "SWE_INSTANCE_ID": "zyc-swe-smith-pytest",
            "PYTHONPATH": "/testbed",
            "PYTHONIOENCODING": "utf-8",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONPATH": "/testbed",
            "PYTHONIOENCODING": "utf-8",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "ALL_PROXY": "http://proxy:mtstudio@10.224.65.111:8235",
            "HTTP_PROXY": "http://proxy:mtstudio@10.224.65.111:8235",
            "HTTPS_PROXY": "http://proxy:mtstudio@10.224.65.111:8235",
            "http_proxy": "http://proxy:mtstudio@10.224.65.111:8235",
            "https_proxy": "http://proxy:mtstudio@10.224.65.111:8235",
            
            # "PIP_INDEX_URL": "http://pip.baidu.com/pypi/simple",
            # "PIP_TRUSTED_HOST": "pip.baidu.com",
        }
        self.resources = resources
        self.name_prefix = name_prefix

        self.kodo_runner = ContainerRunner(
            backend="kubernetes",
            namespace=self.namespace,
            kubeconfig_path=self.kubeconfig_path,
        )
        # 只在“当前 lease”期间存在
        self._pods: dict[str, Any] = {}
        # ... 原有赋值 ...
        self.pod_start_timeout = pod_start_timeout

    
    def _wait_until_exec_ready(self, pod: Any, name: str, timeout: int):
        """
        等待 Pod 可执行：不断尝试一个极轻的 exec（true），
        捕获 404/NotFound/握手异常并重试，直到成功或超时。
        """
        deadline = time.time() + max(5, int(timeout))
        delay = 0.5
        last_err = None
        while time.time() < deadline:
            try:
                _out, code = self.kodo_runner.execute_command(pod, "sh -lc 'true'", timeout=5)
                # 能走到这里且返回码“像样”，说明 exec 通了
                if int(code) in (0, 1, 126, 127, 0):
                    return
            except Exception as e:
                msg = str(e)
                # 常见握手失败/未就绪：继续重试
                if ("NotFound" in msg) or ("404" in msg) or ("not found" in msg) or ("Handshake" in msg):
                    last_err = e
                else:
                    last_err = e  # 其他错误也容忍一会儿
            time.sleep(delay)
            delay = min(delay * 1.5, 5.0)
        raise RuntimeError(f"Pod {name} not exec-ready within {timeout}s: {last_err}")

    # 兼容：允许 with KodoSingleUsePool() as pool: 使用；但不预创建任何容器
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # 正常不残留；若异常中断，尽量清理
        for name, pod in list(self._pods.items()):
            try:
                self.kodo_runner.stop_container(pod)
            finally:
                self._pods.pop(name, None)

    @contextmanager
    def lease(self):
        """启动一个容器 -> 返回名字 -> 用完立刻 stop（删除）"""
        name = f"{self.name_prefix}-{uuid.uuid4().hex[:8]}"
        pod = self.kodo_runner.start_container(
            image=self.image,
            name=name,
            environment=self.environment,
            node_selector=self.node_selector,
            resources=self.resources,
        )
        self._pods[name] = pod
        try:
            yield name
        finally:
            try:
                self.kodo_runner.stop_container(pod)
            finally:
                self._pods.pop(name, None)

    def _ensure_workdir(self, pod: Any):
        cmd = f"sh -lc {shlex.quote(f'mkdir -p {shlex.quote(self.workdir)}')}"
        _out, code = self.kodo_runner.execute_command(pod, cmd)
        if int(code) != 0:
            raise RuntimeError(f"Failed to ensure workdir '{self.workdir}'. exit={code}")

    def exec_script(self, container_name: str, script: str, capture: bool = True, timeout: int = 60) -> ExecResult:
        """
        - 进入 self.workdir 执行脚本
        - 返回值兼容：0/1/124 视为可接受；其余错误也按原逻辑填充 returncode / stderr
        """
        pod = self._pods.get(container_name)
        if pod is None:
            return ExecResult(stdout="", stderr="not found pod", returncode=404)

        try:
            self._ensure_workdir(pod)
            wrapped = f"set -eu; cd {shlex.quote(self.workdir)}; {script}"
            cmd = f"sh -lc {shlex.quote(wrapped)}"
            output, exit_code = self.kodo_runner.execute_command(pod, cmd, timeout=timeout)
            return ExecResult(stdout=output or "", stderr="", returncode=int(exit_code))
        except Exception as e:
            # 不抛异常，保持返回结构一致
            return ExecResult(stdout="", stderr=str(e), returncode=404)

    def force_cleanup_pods(self):
        """
        在外部超时或严重错误时，强制清理此实例已知的所有 Pod。
        这是一个尽力而为（best-effort）的操作。
        """
        if not self._pods:
            return

        print(f"Force cleaning up {len(self._pods)} pod(s) due to external timeout or error.")
        # 使用 list() 创建副本，因为 stop_container 可能会间接修改 self._pods
        for name, pod in list(self._pods.items()):
            try:
                print(f"Force stopping pod: {name}")
                self.kodo_runner.stop_container(pod)
            except Exception as e:
                # 即使一个失败，也要继续尝试清理其他的
                print(f"Failed to force stop pod {name}: {e}", exc_info=True)
            finally:
                # 确保从字典中移除，避免重复清理
                self._pods.pop(name, None)