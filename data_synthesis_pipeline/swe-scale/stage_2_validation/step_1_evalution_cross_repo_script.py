import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import json
import math
import signal
import random
import argparse
from typing import *
from tqdm import tqdm
from pathlib import Path
from contextlib import contextmanager
from multiprocessing import Pool, cpu_count
from concurrent.futures import ThreadPoolExecutor
from utils_list.container_utils.pytest_test_in_container_pool import run_patch_in_container_pool
from utils_list.container_utils.container_single_in_kodo import KodoSingleUsePool
from utils_list.common_utils.common_tools import search_files, load_pkl, dump_pkl
from utils_list.data_structure.constants import INSTANCE_PATH, GROUND_TRUTH, KEY_INSTANCE_ID, KEY_PATCH, KEY_IMAGE_NAME
from stage_0_register_config.register_config import get_all_config, get_config
random.seed(42)
DEFAULT_WORKER_COUNT = 1024


class TimeoutError(Exception):
    """自定义超时异常"""
    pass


@contextmanager
def timeout_context(seconds: int, instance_id: str):
    """
    一个基于 signal 的超时上下文管理器。
    在指定时间后，它会触发一个 TimeoutError。
    注意：这在 Windows 上无效。
    """
    if seconds <= 0:
        yield
        return

    def handler(signum, frame):
        raise TimeoutError(f"Task for instance '{instance_id}' timed out after {seconds} seconds.")

    # 记录旧的信号处理器
    original_handler = signal.signal(signal.SIGALRM, handler)
    try:
        # 设置闹钟
        signal.alarm(seconds)
        yield
    finally:
        # 取消闹钟并将处理器恢复原状
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original_handler)


def run_in_diff_processor(params_list):
    stats = {"Success": 0, "Failed": 0, "Skipped": 0, "Errors": 0}  # 统计指标初始化
    pbar = tqdm(params_list, ncols=120, desc='Evaluation')  # 创建进度条
    for params in pbar:
        try:
            pbar.set_postfix(OK=stats['Success'], FAIL=stats['Failed'], ERROR=stats['Errors'], SKIP=stats['Skipped'])  # 更新进度条后缀
            instance, config, bug_mode = params  # 解构单个参数: (实例数据, 配置对象, 错误模式)
            instance_id = instance['instance_id']  # 获取实例ID
            # setting params - 根据错误模式选择日志目录
            if bug_mode == 'single':
                log_dir_parent = Path(config.LOG_DIR_RUN_EVALUATION)
            else:
                log_dir_parent = Path(config.LOG_DIR_RUN_EVALUATION_COMBINE)
            redo_existing = config.REDO_EXISTING  # 是否重新运行已存在的任务
            # set log dir - 从配置中读取各种参数
            repo_name, commit = config.REPO_NAME, config.COMMIT  # 仓库名称和提交哈希
            image_name = config.IMAGE_NAME  # Docker镜像名称
            docker_workdir = config.DOCKER_WORKDIR  # Docker容器工作目录
            container_concurrency = config.CONTAINER_CONCURRENCY  # 容器并发数
            env_name = config.ENV_NAME  # 环境名称
            timeout = config.PYTEST_TIMEOUT  # pytest超时时间
            docker_workdir = config.DOCKER_WORKDIR  # 重复的赋值，可能是个bug
            # 检查是否已成功完成，避免重复执行
            if os.path.exists(str(log_dir_parent / instance_id / f'{INSTANCE_PATH}__SUCCESS__')):
                stats['Skipped'] += 1
                continue
            resources = config.RESOURCES  # 容器资源限制
            redirect = config.REDIRECT  # 是否重定向输出
            xml_report = config.XML_REPORT  # 是否生成XML报告
            script = config.TEST_SCRIPT  # 测试脚本路径
            os.environ['KUBECONFIG'] = config.KUBECONFIG  # 设置k8s配置文件
            if hasattr(config, 'LLM_NAMESPACE'):
                os.environ['LLM_NAMESPACE'] = config.LLM_NAMESPACE  # 设置LLM命名空间
            else:
                os.environ['LLM_NAMESPACE'] = 'data-synthesis'  # 默认命名空间
            
            # 创建Kodo容器池，用于运行测试
            pool = KodoSingleUsePool(
                image=image_name, 
                workdir=docker_workdir, 
                resources=resources, 
                name_prefix='zyc-swe-smith-{}'.format(repo_name.replace('/', '-').replace('_', '-'))[:32].lower()  # 容器名前缀
            )
            external_timeout = max(1200, timeout) + 100  # 设置外部超时时间(最小1300秒)
            with timeout_context(external_timeout, instance_id):  # 超时保护上下文
                # 在容器池中运行补丁测试脚本
                flag = run_patch_in_container_pool(
                    instance,
                    log_dir_parent / instance_id,  # 日志目录
                    pool,
                    env_name=env_name,
                    docker_workdir=docker_workdir,
                    script=script,
                    redirect=True,  # 强制重定向输出
                    redirect_report=True,  # 重定向报告
                    timeout=max(1200, timeout)  # 内部超时时间
                )
            if flag:  # 测试成功
                stats['Success'] += 1
                instance['log_parser'] = config.PYTEST_LOG_PARSER  # 添加日志分析器信息
                open(log_dir_parent / instance_id / f'{INSTANCE_PATH}__SUCCESS__', 'w').close()  # 创建成功标记文件
                with open(log_dir_parent / instance_id / INSTANCE_PATH, 'w') as f:
                    json.dump(instance, f, ensure_ascii=False, indent=4)  # 保存实例数据到JSON文件
            else:  # 测试失败
                stats['Failed'] += 1
        except TimeoutError as e:  # 处理超时异常
            stats['Errors'] += 1
            print(f"\n[ERROR] Task for {instance_id} was terminated due to timeout: {e}")
            if pool:
                pool.force_cleanup_pods()  # 强制清理k8s pods
            continue
        except Exception as e:  # 处理其他异常
            stats['Errors'] += 1
            print(f"\n[ERROR] An unexpected error occurred for {instance_id}: {e}")
            if pool:
                pool.force_cleanup_pods()
            continue
        finally:
            pbar.set_postfix(OK=stats['Success'], FAIL=stats['Failed'], ERROR=stats['Errors'], SKIP=stats['Skipped'])  # 最终更新进度条
    pbar.close()
    # 打印最终统计结果
    print(
        f"Total: {len(params_list)}", 
        f"Success: {stats['Success']}",
        f"Failed: {stats['Failed']}",
        f"Errors: {stats['Errors']}",
        f"Skipped: {stats['Skipped']}"
    )
    del params_list  # 清理内存


def collection_patch(config, bug_mode):
    if bug_mode == 'single':
        log_dir_run_evaluation = Path(config.LOG_DIR_RUN_EVALUATION)
        log_dir_bug_gen = Path(config.LOG_DIR_BUG_GEN)
    else:
        log_dir_run_evaluation = Path(config.LOG_DIR_RUN_EVALUATION_COMBINE)
        log_dir_bug_gen = Path(config.LOG_DIR_BUG_GEN_COMBINE)
    repo_name, commit, image_name = config.REPO_NAME, config.COMMIT, config.IMAGE_NAME
    
    log_dir_run_evaluation.mkdir(parents=True, exist_ok=True)
    file_path_list = set(search_files(log_dir_bug_gen))
    success_path_set = set(search_files(log_dir_run_evaluation))
    candidate_params_list = []
    completed = 0
    for file_path in file_path_list:
        if not file_path.endswith(".diff"):
            continue
        bug_type_and_uuid = os.path.basename(file_path).split(".diff")[0]
        instance_id = f"{repo_name}.{bug_type_and_uuid}"
        success_path = log_dir_run_evaluation / instance_id / '{}__SUCCESS__'.format(INSTANCE_PATH)
        if str(success_path) in success_path_set:
            completed += 1
            continue
        patch = {
            KEY_INSTANCE_ID: instance_id,
            KEY_PATCH: open(file_path, 'r').read(),
            KEY_IMAGE_NAME: image_name,
            "repo": repo_name,
            "commit": commit,
            'file_path': file_path,
            'log_parser': config.PYTEST_LOG_PARSER
        }
        candidate_params_list.append([patch, config, bug_mode])
    print(f"Found {completed} completed evaluations. Remaining: {len(candidate_params_list)}")
    return candidate_params_list


def evaluation_parallel(config, bug_mode):
    total_params_list = collection_patch(config, bug_mode)

    params_list = []
    chunk_size = math.ceil(len(total_params_list) / DEFAULT_WORKER_COUNT)
    for index in tqdm(range(0, DEFAULT_WORKER_COUNT), ncols=70):
        tmp_params_list = total_params_list[index * chunk_size: (index + 1) * chunk_size]
        params_list.append(tmp_params_list)

    # for params in params_list:
    #     run_in_diff_processor(params)

    with Pool(processes=DEFAULT_WORKER_COUNT) as p:
        p.map(run_in_diff_processor, params_list)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluation parallel"
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    parser.add_argument(
        "--bug_mode", type=str, help="Bug mode", choices=["combine", "single"], default='single'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    evaluation_parallel(config, args.bug_mode)
