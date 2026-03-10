import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import json
import random
import argparse
from typing import *
from tqdm import tqdm
from pathlib import Path
from multiprocessing import Pool
from utils_list.container_utils.pytest_test_in_container_pool import run_patch_in_container_pool
from utils_list.container_utils.container_single_in_kodo import KodoSingleUsePool
from utils_list.common_utils.common_tools import search_files
from utils_list.data_structure.constants import INSTANCE_PATH, GROUND_TRUTH, LOG_JSON_REPORT_OUTPUT
from stage_0_register_config.register_config import get_all_config, get_config


def run_in_diff_processor(params):
    try:
        instance, config, run_id = params
        instance_id = instance['instance_id']
        # setting params
        log_dir_run_evaluation = config.LOG_DIR_RUN_EVALUATION
        # set log dir
        log_dir_parent = Path(os.path.join(log_dir_run_evaluation, run_id))
        # if os.path.exists(os.path.join(str(log_dir_parent), str(INSTANCE_PATH) + '__SUCCESS__')):
        #     return
        os.makedirs(log_dir_parent, exist_ok=True)
        repo_name, commit = config.REPO_NAME, config.COMMIT
        image_name = config.IMAGE_NAME
        docker_workdir = config.DOCKER_WORKDIR
        container_concurrency = config.CONTAINER_CONCURRENCY
        env_name = config.ENV_NAME
        timeout = config.PYTEST_TIMEOUT
        docker_workdir = config.DOCKER_WORKDIR
        script = config.TEST_SCRIPT

        resources = config.RESOURCES
        redirect = config.REDIRECT
        xml_report = config.XML_REPORT
        os.environ['KUBECONFIG'] = config.KUBECONFIG
        if hasattr(config, 'LLM_NAMESPACE'):
            os.environ['LLM_NAMESPACE'] = config.LLM_NAMESPACE
        else:
            os.environ['LLM_NAMESPACE'] = 'data-synthesis'
        flag = run_patch_in_container_pool(
            instance,
            log_dir_parent,
            KodoSingleUsePool(
                image=image_name, 
                workdir=docker_workdir, 
                resources=resources, 
                name_prefix='zyc-swe-smith-{}'.format(repo_name.replace('/', '-').replace('_', '-'))[:32].lower()
            ),
            env_name=env_name,
            docker_workdir=docker_workdir,
            script=script,
            redirect=redirect,
            redirect_report=xml_report,
            timeout=max(1200, timeout)
        )
        if flag:
            instance['log_parser'] = config.PYTEST_LOG_PARSER
            open(os.path.join(str(log_dir_parent), str(INSTANCE_PATH) + '__SUCCESS__'), 'w').close()
            with open(os.path.join(str(log_dir_parent), str(INSTANCE_PATH)), 'w') as f:
                json.dump(instance, f, ensure_ascii=False, indent=4)
        return flag
    except Exception as e:
        return False


def evaluation_ground_truth(config):
    params_list = []
    for index in range(0, 10):
        ground_truth = {
            "cost": 0,
            "explanation": None,
            "output": None,
            "rewrite": None,
            "strategy": None,
            "instance_id": GROUND_TRUTH,
            "patch": None,
            "image_name": config.IMAGE_NAME,
            "repo": config.REPO_NAME,
            "commit": config.COMMIT,
            "file_path": None
        }
        params_list.append([ground_truth, config, GROUND_TRUTH + '_%.4d' % index])
    
    print('params size', len(params_list))
    for params in params_list:
        run_in_diff_processor(params)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluation parallel"
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    evaluation_ground_truth(config)

