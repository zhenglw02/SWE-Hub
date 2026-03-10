import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import json
import shlex
import uuid
import queue
import textwrap
import subprocess
from contextlib import contextmanager
from typing import *
from pathlib import Path
from utils_list.container_utils.container_pool import ContainerPool


def to_container_path(candidate_file_path: str, host_repo_root: str, repo_workdir: str) -> str:
    """
    将 candidate.file_path 映射为容器内 path。
    - 如果是绝对路径：必须位于 host_repo_root 之下；转为相对并拼到 repo_workdir。
    - 如果是相对路径：直接拼到 repo_workdir。
    """
    host_repo_root = os.path.normpath(host_repo_root)
    p = Path(candidate_file_path)
    if p.is_absolute():
        norm_p = os.path.normpath(str(p))
        common = os.path.commonpath([host_repo_root, norm_p])
        if common != host_repo_root:
            raise ValueError(f"file_path 不在 host_repo_root 下：\n  file_path={p}\n  host_repo_root={host_repo_root}")
        rel = os.path.relpath(norm_p, host_repo_root)
        return str(Path(repo_workdir) / rel)
    else:
        return str(Path(repo_workdir) / candidate_file_path)


def apply_change_and_get_patch_in_pool(
    candidate,
    bug,
    *,
    pool,
    host_repo_root: str,
    repo_workdir: str = "/testbed",
    reset_changes: bool = True,
) -> Optional[str]:
    """
    在“只有 sh 的容器”里复用容器池，修改 /testbed 下文件并输出 patch。
    - 自动把宿主路径映射成容器路径
    - 预检：git/python/目标文件存在；safe.directory 防止 git 可疑所有权报错
    - 成功/失败都会按 reset_changes 恢复干净（trap + 兜底）
    """
    # --- 1) 计算容器内文件路径 ---
    container_file_path = to_container_path(candidate.file_path, host_repo_root, repo_workdir)

    # --- 2) 容器内执行的 Python 片段（只负责改文件） ---
    py_inline = f"""
from pathlib import Path

file_path = {container_file_path!r}
line_start = {candidate.line_start}
line_end   = {candidate.line_end}
indent_level = {candidate.indent_level}
indent_size  = {candidate.indent_size}
replacement  = {bug.rewrite!r}

p = Path(file_path)
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
if line_start < 1 or line_end > len(lines) or line_start > line_end:
    raise ValueError("Invalid line range specified.")
replacement_lines = [
    (" " * indent_level * indent_size + x) if x.strip() else x
    for x in replacement.splitlines(keepends=True)
]
new_lines = lines[: line_start - 1] + replacement_lines + lines[line_end :]
p.write_text("".join(new_lines), encoding="utf-8")
"""

    # --- 3) 清理脚本（sh 兼容） ---
    cleanup_sh = textwrap.dedent("""
        git restore --staged . >/dev/null 2>&1 || true
        git reset --hard       >/dev/null 2>&1 || true
        git clean -fdx         >/dev/null 2>&1 || true
    """).strip()

    # --- 4) 组合容器内脚本：sh-only、带 trap、自检更友好 ---
    file_q = shlex.quote(container_file_path)
    workdir_q = shlex.quote(repo_workdir)

    trap_line = "trap cleanup EXIT" if reset_changes else ": # no cleanup trap"

    script = "\n".join([
        "set -eu",
        f"cd {workdir_q}",
        "",
        # 预检工具
        'if ! command -v git >/dev/null 2>&1; then echo "git not found" >&2; exit 127; fi',
        'PYBIN=$(command -v python3 || command -v python || true)',
        'if [ -z "${PYBIN:-}" ]; then echo "No python interpreter found" >&2; exit 127; fi',
        'git config --global --add safe.directory "$(pwd)" >/dev/null 2>&1 || true',

        # ✅ 新增：生成补丁前，先把仓库清干净，避免把历史残留写进 patch
        "git restore --staged . >/dev/null 2>&1 || true",
        "git reset --hard       >/dev/null 2>&1 || true",
        "git clean -fdx         >/dev/null 2>&1 || true",
        "",

        # 预检文件是否存在
        f"if [ ! -f {file_q} ]; then echo 'Missing file in container: {container_file_path}' >&2; exit 66; fi",

        # 清理函数 + trap
        "cleanup() {",
        cleanup_sh,
        "}",
        trap_line,
        "",

        # 改文件
        "cat <<'PY' | \"$PYBIN\" -",
        py_inline,
        "PY",

        # ✅ 修改：只暂存这个文件，而不是 add -A
        f"git add -- {file_q}",

        # 生成 patch（保持你的 -M -C --binary）
        "git diff --staged -M -C --binary || true",
    ])

    # --- 5) 执行 + 兜底清理 ---
    try:
        with pool.lease() as name:
            proc = pool.exec_script(name, script, capture=True)
            patch = proc.stdout  # 保留原样，包含末尾换行
            return patch if patch.strip() else None
    except Exception:
        # 兜底：当 docker exec 自身失败/脚本没跑起来时尝试清理一次
        if reset_changes:
            try:
                with pool.lease() as name2:
                    pool.exec_script(name2, f"set -eu; cd {workdir_q}; {cleanup_sh}", capture=False)
            except Exception:
                pass
        raise


def apply_patches_with_pool(
    repo: str,
    patch_files: list[str],
    *,
    pool: ContainerPool,
    repo_workdir: str = "/testbed",
) -> Optional[str]:
    """
    在容器池中将多个补丁应用到仓库并生成“合并后的单个 patch”。
    采用稳 + 可解释策略：
      1) 按原顺序逐个 `git apply`
      2) 同顺序再试一次：`git apply --3way --whitespace=nowarn`
      3) 若有 >=2 个补丁，反序再试：`--3way --whitespace=nowarn`
      4) 全部失败则返回 None（可在需要时添加 --reject 诊断流程）
    生成后的 patch 使用 `git apply --check` 在“干净树”上验证可重放。
    """
    # 读取宿主机上的补丁内容
    patch_texts: List[str] = []
    for pf in patch_files:
        if not os.path.isfile(pf):
            return None
        with open(pf, "r", encoding="utf-8") as f:
            c = f.read()
        if c.strip():
            patch_texts.append(c)
    if not patch_texts:
        return None

    # 尝试序列：先原顺序，必要时再反序
    orders: List[List[str]] = [patch_texts]
    if len(patch_texts) > 1:
        orders.append(list(reversed(patch_texts)))

    # 应用策略：先严格，再稳健
    apply_opts_candidates = ["", "--3way --whitespace=nowarn"]

    def _build_script(seq: List[str], opts: str, merged_tmp: str) -> str:
        """
        构造一次完整尝试的容器内脚本：
          - 保持 POSIX sh 兼容（不使用 pipefail）
          - /tmp 写入各补丁并按 {opts} 逐个 git apply
          - 生成合并 patch 到 /tmp，清理到干净树后 --check 校验，再输出
        """
        cleanup_sh = """
            git restore --staged . >/dev/null 2>&1 || true
            git reset --hard       >/dev/null 2>&1 || true
            git clean -fdx         >/dev/null 2>&1 || true
        """.strip()

        lines = [
            "set -eu",
            f"cd {shlex.quote(repo_workdir)}",
            'if ! command -v git >/dev/null 2>&1; then echo "git not found" >&2; exit 127; fi',
            'git config --global --add safe.directory "$(pwd)" >/dev/null 2>&1 || true',
            # 定义清理，并保证开始前干净
            "cleanup() {",
            cleanup_sh,
            "}",
            "trap cleanup EXIT",
            "cleanup",
        ]

        # 逐个写入补丁并应用
        for i, content in enumerate(seq):
            tag = f"PATCH_{i}_{uuid.uuid4().hex[:8]}"
            pth = f"/tmp/{tag}.patch"
            lines += [
                f"cat > {shlex.quote(pth)} <<'__{tag}__'",
                content,
                f"__{tag}__",
            ]
            # 选择性加入 apply 选项
            if opts:
                lines.append(f"git apply {opts} {shlex.quote(pth)}")
            else:
                lines.append(f"git apply {shlex.quote(pth)}")

        # 生成合并 patch（仓库外的 /tmp），清理，干净树上做 --check，最后输出
        lines += [
            "git add -A >/dev/null",
            f"git diff --staged -M -C --binary > {shlex.quote(merged_tmp)} || true",
            f"[ -s {shlex.quote(merged_tmp)} ] || exit 65",
            "cleanup",
            f"git apply --check {shlex.quote(merged_tmp)}",
            f"cat {shlex.quote(merged_tmp)}",
        ]
        return "\n".join(lines)

    # 依次尝试（顺序 × apply 选项）
    for opts in apply_opts_candidates:
        for seq in orders:
            merged_tmp = f"/tmp/merged-{uuid.uuid4().hex}.patch"
            script = _build_script(seq, opts, merged_tmp)
            try:
                with pool.lease() as name:
                    proc = pool.exec_script(name, script, capture=True)
                    merged = (proc.stdout or "").strip()
                    if merged:
                        return merged
            except Exception:
                # 本次尝试失败，继续下一种策略或顺序
                continue

    # （可选）如果需要更“可解释”的失败信息，可在这里追加一次 --reject 诊断尝试
    # 比如收集 .rej 数量并打印到 stderr；但本函数签名只返回 patch/None，默认为不输出诊断。
    return None

