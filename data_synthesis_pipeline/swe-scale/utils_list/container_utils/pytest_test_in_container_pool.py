import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import json
import time
import shlex
import random
from typing import *
from pathlib import Path
from logging import Logger
from swebench.harness.utils import EvaluationError
from swebench.harness.docker_build import setup_logger, close_logger
from utils_list.container_utils.container_pool import ContainerPool, ExecResult
from utils_list.data_structure.constants import *
random.seed(42)


def _exec_on(pool: ContainerPool, container_name: str, script: str, capture: bool = True, timeout: int = 60):
    return pool.exec_script(container_name, script, capture=capture, timeout=timeout)


def _reset_repo_head_on(pool, container_name: str, workdir: str):
    scr = "\n".join([
        "set -eu",
        f"cd {shlex.quote(workdir)}",
        'git config --global --add safe.directory "$(pwd)" >/dev/null 2>&1 || true',
        "git restore --staged . >/dev/null 2>&1 || true",
        "git reset --hard       >/dev/null 2>&1 || true",
        "git clean -fd         >/dev/null 2>&1 || true",
        "git config core.autocrlf false >/dev/null 2>&1 || true"
    ])
    return _exec_on(pool, container_name, scr, capture=False)


def _apply_patch_in_pool(
    instance_id: str,
    pool: ContainerPool,
    logger: Logger,
    *,
    container_name: str,
    workdir: str,
    patch_path: str,
    is_gold: bool = False,
):
    workdir_q = shlex.quote(workdir)
    patch_q = shlex.quote(patch_path)

    cleanup_sh = """
        git restore --staged . >/dev/null 2>&1 || true
        git reset --hard       >/dev/null 2>&1 || true
        git clean -fd         >/dev/null 2>&1 || true
    """.strip()

    # 已应用检测：正向不行但反向 --check 通过，视为已应用
    precheck = "\n".join([
        "set -eu",
        f"cd {workdir_q}",
        f"git apply --check -p1 {patch_q} >/dev/null 2>&1 || true",
        'echo FWD=$?',
        f"git apply --reverse --check -p1 {patch_q} >/dev/null 2>&1 || true",
        'echo REV=$?',
    ])
    res = _exec_on(pool, container_name, precheck, capture=True)
    out = res.stdout or ""
    fwd_rc = next((int(l.split('=')[1]) for l in out.splitlines() if l.startswith("FWD=")), 1)
    rev_rc = next((int(l.split('=')[1]) for l in out.splitlines() if l.startswith("REV=")), 1)
    if fwd_rc != 0 and rev_rc == 0:
        logger.info("Patch already present (reverse --check passes); treat as success.")
        return res

    def _build_apply_script(direction_reverse: bool, pstrip: int, opts: str) -> str:
        rev = "--reverse " if direction_reverse else ""
        p   = f"-p{pstrip} " if pstrip is not None else ""
        return f"""\
set -eu
cd {workdir_q}
if ! command -v git >/dev/null 2>&1; then
  echo "git not found" >&2
  exit 127
fi
git config --global --add safe.directory "$(pwd)" >/dev/null 2>&1 || true

if ! git apply {opts} {rev}{p}{patch_q}; then
  echo "---- git apply failed ----" >&2
  git status --porcelain || true
  ls -R | grep -E '\\.rej$' -n || true
  {cleanup_sh}
  exit 1
fi
exit 0
"""

    dir_order = ([True, False] if is_gold else [False, True])
    p_candidates = [1, 0, 2]
    # 多一档“鲁棒选项”可抗空白/EOL 漂移
    opts_candidates = [
        "",  # 严格
        "-3 --recount --whitespace=nowarn",  # 三方
        "--reject --recount --ignore-space-change --inaccurate-eof --whitespace=nowarn",  # 鲁棒
    ]

    tries, last_err = [], None
    for rev_flag in dir_order:
        for p in p_candidates:
            for opts in opts_candidates:
                tries.append((rev_flag, p, opts))

    for rev_flag, p, opts in tries:
        script = _build_apply_script(rev_flag, p, opts)
        try:
            res = _exec_on(pool, container_name, script, capture=True, )
            logger.info(
                f"APPLY_PATCH_PASS: direction={'reverse' if rev_flag else 'forward'}, "
                f"-p{p}, opts={'<strict>' if not opts else opts}"
            )
            return res
        except Exception as e:
            last_err = e
            logger.info(
                f"Failed to apply patch: direction={'reverse' if rev_flag else 'forward'}, "
                f"-p{p}, opts={'<strict>' if not opts else opts}\n{e}\nTrying next..."
            )

    try:
        diag = _exec_on(
            pool, container_name,
            "\n".join(["set -eu", f"cd {workdir_q}", r"ls -R | grep -E '\.rej$' -n || true"]),
            capture=True
        )
        rej_ls = diag.stdout or ""
    except Exception:
        rej_ls = ""

    err_msg = f"{APPLY_PATCH_FAIL}:\n{last_err}\n.rej files:\n{rej_ls}"
    logger.info(err_msg)
    raise EvaluationError(instance_id, err_msg, logger)


def run_patch_in_container_pool(
    instance: dict,
    log_dir: Path,
    pool: ContainerPool,
    env_name: str,
    docker_workdir: str,
    script: str,
    redirect: bool = False,
    redirect_report: bool = False,
    timeout: int = 300,
    _conda_dir="/opt/miniconda3",
    _conda_env="testbed",
) -> bool:
    """
    使用 ContainerPool 跑完整评测：
      1) 写 patch（可选）到容器、并应用
      2) 写 eval.sh 到容器
      3) timeout 执行测试，抓取输出和超时态
    返回 (logger, timed_out)；出错时返回 None。
    """
    # 0) 日志
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(log_dir / LOG_INSTANCE, log_dir / LOG_INSTANCE)

    instance_id = instance["instance_id"]
    patch = instance.get('patch')
    # commit = instance.get("commit")
    commit = None

    with pool.lease() as name:
        # print(f"pod: {name}")
        # 1) 先回到固定基线（当前 HEAD 的干净树）
        res = _reset_repo_head_on(pool, name, docker_workdir)
        if int(res.returncode) != 0:
            logger.info(f"RESET FAILED:\n{res.stdout}\n{res.stderr}")
            close_logger(logger)
            return False
        # 2) （可选）checkout 本地存在的 commit（不联网）
        if commit:
            scr = "\n".join([
                "set -eux",
                f"cd {shlex.quote(docker_workdir)}",
                "export GIT_TERMINAL_PROMPT=0",
                f"if git rev-parse --verify --quiet {shlex.quote(commit)} >/dev/null; then",
                f"  git -c advice.detachedHead=false checkout --force {shlex.quote(commit)}",
                "else",
                f"  echo 'ERROR: commit/ref {commit} not found locally; network operations are disabled.' >&2",
                "  exit 66",
                "fi",
            ])
            res = _exec_on(pool, name, scr, capture=True)
            if int(res.returncode) != 0:
                logger.info(f"CHECKOUT FAILED:\n{res.stdout}\n{res.stderr}")
                close_logger(logger)
                return False

        # 3) 写入补丁并应用（在同一个容器）
        if patch:
            tag = f"PATCH_{os.getpid()}_{os.urandom(4).hex()}"
            res = _exec_on(pool, name, "\n".join([
                "set -eu",
                f"cat > {shlex.quote(DOCKER_PATCH)} <<'__{tag}__'",
                patch,
                f"__{tag}__",
            ]), capture=False)
            if int(res.returncode) != 0:
                logger.info(f"APPLY FAILED:\n{res.stdout}\n{res.stderr}")
                close_logger(logger)
                return False
            res = _apply_patch_in_pool(
                instance_id, pool, logger,
                container_name=name,
                workdir=docker_workdir,
                patch_path=DOCKER_PATCH,
            )
            if int(res.returncode) != 0:
                logger.info(f"APPLY FAILED:\n{res.stdout}\n{res.stderr}")
                close_logger(logger)
                return False
        new_exec_command = script
        if redirect_report:
            new_exec_command = new_exec_command + ' --junitxml={}'.format(str(log_dir / LOG_XML_REPORT_OUTPUT))
        if redirect:
            new_exec_command = new_exec_command + '> {}'.format(str(log_dir / LOG_TEST_OUTPUT))
        # 4) 写 eval.sh（同容器）
        eval_sh = "\n".join([
            "#!/bin/sh",
            "set -u",
            f"cd {shlex.quote(docker_workdir)}",
            'if [ -f "/opt/miniconda3/bin/activate" ]; then . /opt/miniconda3/bin/activate || true; fi',
            f'if command -v conda >/dev/null 2>&1; then conda activate {shlex.quote(env_name)} || true; fi',
            f"echo {shlex.quote(TESTS_OUTPUT_START)}",
            'if command -v bash >/dev/null 2>&1; then RUN_SHELL="bash -lc"; else RUN_SHELL="sh -lc"; fi',
            "RC=0",
            "if command -v timeout >/dev/null 2>&1; then",
            "  set +e",
            f"  timeout {int(timeout)}s $RUN_SHELL {shlex.quote(new_exec_command)}",
            "  RC=$?",
            "  set -e || true",
            "else",
            '  echo "[warn] timeout not found; running without time limit" >&2',
            "  set +e",
            f"  $RUN_SHELL {shlex.quote(new_exec_command)}",
            "  RC=$?",
            "  set -e || true",
            "fi",
            f"echo {shlex.quote(TESTS_OUTPUT_END)}",
            'echo "RC=${RC}"',
            "exit 0",
            ""
        ])
        res = _exec_on(pool, name, "\n".join([
            "set -eu",
            "cat > /eval.sh <<'__EVAL__'",
            eval_sh,
            "__EVAL__",
            "chmod +x /eval.sh",
        ]), capture=False)

        if int(res.returncode) != 0:
            logger.info(f"PYTEST FAILED:\n{res.stdout}\n{res.stderr}")
            close_logger(logger)
            return False

        exec_command = '. {}/etc/profile.d/conda.sh && conda activate {} && {}'.format(
            _conda_dir, _conda_env,        
            "/bin/sh /eval.sh"
        )

        # 5) 执行 eval.sh（同容器）
        res = _exec_on(pool, name, exec_command, capture=True, timeout=timeout)
        out = res.stdout     
        timed_out = (int(res.returncode) == 124)

        if not redirect:
            (log_dir / LOG_TEST_OUTPUT).write_text(out, encoding=UTF8)

        eval_sh = "\n".join([
            "#!/bin/sh",
            "set -u",
            f"cd {shlex.quote(docker_workdir)}",
            'if [ -f "/opt/miniconda3/bin/activate" ]; then . /opt/miniconda3/bin/activate || true; fi',
            f'if command -v conda >/dev/null 2>&1; then conda activate {shlex.quote(env_name)} || true; fi',
            f"echo {shlex.quote(TESTS_OUTPUT_START)}",
            'if command -v bash >/dev/null 2>&1; then RUN_SHELL="bash -lc"; else RUN_SHELL="sh -lc"; fi',
            "RC=0",
            "if command -v timeout >/dev/null 2>&1; then",
            "  set +e",
            f"  timeout {int(timeout)}s $RUN_SHELL {shlex.quote(new_exec_command)}",
            "  RC=$?",
            "  set -e || true",
            "else",
            '  echo "[warn] timeout not found; running without time limit" >&2',
            "  set +e",
            f"  $RUN_SHELL {shlex.quote(new_exec_command)}",
            "  RC=$?",
            "  set -e || true",
            "fi",
            f"echo {shlex.quote(TESTS_OUTPUT_END)}",
            'echo "RC=${RC}"',
            "exit 0",
            ""
        ])     
        (log_dir / LOG_EVAL_SH).write_text(eval_sh, encoding=UTF8)
        logger.info(f"Test exit code marker: {int(res.returncode)!r} (timed_out={timed_out})")        
        logger.info(f"Test error messages: {res.stderr}")
        logger.info(f"Test output for {instance_id} written to {log_dir/LOG_TEST_OUTPUT}")

        # 收尾：清干净，方便下轮复用同一容器
        _reset_repo_head_on(pool, name, docker_workdir)

    close_logger(logger)
    return int(res.returncode) in [0, 1]


def run_patch_in_container_pool_script(
    instance: dict,
    log_dir: Path,
    pool: ContainerPool,
    env_name: str,
    docker_workdir: str,
    script: str,
    redirect: bool = False,
    redirect_report: bool = False,
    timeout: int = 300,
    _conda_dir="/opt/miniconda3",
    _conda_env="testbed",
) -> bool:
    """
    使用 ContainerPool 跑完整评测：
      1) 写 patch（可选）到容器、并应用
      2) 写 eval.sh 到容器
      3) timeout 执行测试，抓取输出和超时态
    返回 (logger, timed_out)；出错时返回 None。
    """
    # 0) 日志
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(log_dir / LOG_INSTANCE, log_dir / LOG_INSTANCE)

    instance_id = instance["instance_id"]
    patch = instance.get('patch')
    # commit = instance.get("commit")
    commit = None

    with pool.lease() as name:
        # print(f"pod: {name}")
        # 1) 先回到固定基线（当前 HEAD 的干净树）
        res = _reset_repo_head_on(pool, name, docker_workdir)
        if int(res.returncode) != 0:
            logger.info(f"RESET FAILED:\n{res.stdout}\n{res.stderr}")
            close_logger(logger)
            return False
        # 2) （可选）checkout 本地存在的 commit（不联网）
        if commit:
            scr = "\n".join([
                "set -eux",
                f"cd {shlex.quote(docker_workdir)}",
                "export GIT_TERMINAL_PROMPT=0",
                f"if git rev-parse --verify --quiet {shlex.quote(commit)} >/dev/null; then",
                f"  git -c advice.detachedHead=false checkout --force {shlex.quote(commit)}",
                "else",
                f"  echo 'ERROR: commit/ref {commit} not found locally; network operations are disabled.' >&2",
                "  exit 66",
                "fi",
            ])
            res = _exec_on(pool, name, scr, capture=True)
            if int(res.returncode) != 0:
                logger.info(f"CHECKOUT FAILED:\n{res.stdout}\n{res.stderr}")
                close_logger(logger)
                return False

        # 3) 写入补丁并应用（在同一个容器）
        if patch:
            tag = f"PATCH_{os.getpid()}_{os.urandom(4).hex()}"
            res = _exec_on(pool, name, "\n".join([
                "set -eu",
                f"cat > {shlex.quote(DOCKER_PATCH)} <<'__{tag}__'",
                patch,
                f"__{tag}__",
            ]), capture=False)
            if int(res.returncode) != 0:
                logger.info(f"APPLY FAILED:\n{res.stdout}\n{res.stderr}")
                close_logger(logger)
                return False
            res = _apply_patch_in_pool(
                instance_id, pool, logger,
                container_name=name,
                workdir=docker_workdir,
                patch_path=DOCKER_PATCH,
            )
            if int(res.returncode) != 0:
                logger.info(f"APPLY FAILED:\n{res.stdout}\n{res.stderr}")
                close_logger(logger)
                return False

        res = _exec_on(pool, name, "\n".join([
            "set -eu",
            "cat > /eval.sh <<'__EVAL__'",
            script,
            "__EVAL__",
            "chmod +x /eval.sh",
        ]), capture=False)
        if int(res.returncode) != 0:
            logger.info(f"PYTEST FAILED:\n{res.stdout}\n{res.stderr}")
            close_logger(logger)
            return False
    
        exec_command = '. {}/etc/profile.d/conda.sh && conda activate {} && {}'.format(
            _conda_dir, _conda_env,        
            "/bin/sh /eval.sh" + ' > {}'.format(str(log_dir / LOG_TEST_OUTPUT))
        )
        # 5) 执行 eval.sh（同容器）
        res = _exec_on(pool, name, exec_command, capture=True, timeout=timeout)
        out = res.stdout     
        timed_out = (int(res.returncode) == 124)

        if not redirect:
            (log_dir / LOG_TEST_OUTPUT).write_text(out, encoding=UTF8)

        if redirect_report:
            report_json_in_pod = "cp /testbed/standard_result.json {}".format(str(log_dir / LOG_JSON_REPORT_OUTPUT))
            res = _exec_on(pool, name, report_json_in_pod, capture=True, timeout=timeout)

        (log_dir / LOG_EVAL_SH).write_text(script, encoding=UTF8)
        logger.info(f"Test exit code marker: {int(res.returncode)!r} (timed_out={timed_out})")        
        logger.info(f"Test error messages: {res.stderr}")
        logger.info(f"Test output for {instance_id} written to {log_dir/LOG_TEST_OUTPUT}")

        # 收尾：清干净，方便下轮复用同一容器
        _reset_repo_head_on(pool, name, docker_workdir)

    close_logger(logger)
    return int(res.returncode) in [0, 1]