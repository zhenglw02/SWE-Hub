import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import json
import math
import random
import argparse
from typing import *
from tqdm import tqdm
from pathlib import Path
from timeout_decorator import TimeoutError
from multiprocessing import Pool, cpu_count
from concurrent.futures import ThreadPoolExecutor
from utils_list.container_utils.pytest_test_in_container_pool import run_patch_in_container_pool
from utils_list.container_utils.container_single_in_kodo import KodoSingleUsePool
from utils_list.common_utils.common_tools import search_files, my_os_walk, load_pkl, dump_pkl
from utils_list.data_structure.constants import (
    GROUND_TRUTH, LOG_TEST_OUTPUT, LOG_REPORT, 
    FAIL_TO_PASS, PASS_TO_PASS,
    FAIL_TO_FAIL, PASS_TO_FAIL,
    LOG_JSON_REPORT_OUTPUT
)
from utils_list.parser_utils.pytest_log_parsers import MAP_REPO_TO_PARSER
from stage_0_register_config.register_config import get_all_config


def gen_report(params):
    instance_id, log_dir_parent, test_output_path, pass_set, fail_set = params
    # if os.path.exists(str(log_dir_parent / instance_id / LOG_REPORT) + '__SUCCESS__'):
    #     return True
    test_case_result_dict = {}
    test_case_result_list = json.load(open(test_output_path, 'r'))
    for item in test_case_result_list:
        test_name = '{}::{}'.format(item['file'], item['test_name'])
        if item['status'] == 'passed':
            value = 'PASSED'
        else:
            value = 'FAILED'
        test_case_result_dict[test_name] = value

    if len(test_case_result_dict) == 0:    
        open(str(log_dir_parent / instance_id / LOG_REPORT) + '__SUCCESS__', "w")
        return False
    report_dict = {}
    f2p, p2p, f2f, p2f = [], [], [], []
    for test_case, status in test_case_result_dict.items():
        if status == 'PASSED':
            if test_case in pass_set:
                p2p.append(test_case)
            elif test_case in fail_set:
                f2p.append(test_case)
        elif status == 'FAILED':
            if test_case in pass_set:
                p2f.append(test_case)
            elif test_case in fail_set:
                f2f.append(test_case)
        else:
            continue
    # 注意，这里要逆转过来
    report_dict = {
        FAIL_TO_PASS: p2f,
        PASS_TO_PASS: p2p,
        FAIL_TO_FAIL: f2f,
        PASS_TO_FAIL: f2p,
    }
    json.dump(report_dict, open(log_dir_parent / instance_id / LOG_REPORT, "w"), indent=4, ensure_ascii=False)
    open(str(log_dir_parent / instance_id / LOG_REPORT) + '__SUCCESS__', "w")
    return True


def gen_report_file(params):
    config, bug_mode = params
    if bug_mode == 'single':
        log_dir_parent = Path(config.LOG_DIR_RUN_EVALUATION)
    else:
        log_dir_parent = Path(config.LOG_DIR_RUN_EVALUATION_COMBINE)
    ground_truth_path = str(Path(config.LOG_DIR) / (GROUND_TRUTH+ '.json'))
    if not os.path.exists(ground_truth_path):
        return
    ground_truth_dict = json.load(open(ground_truth_path, 'r'))
    pass_set, fail_set = set(), set()
    for test_case, status in ground_truth_dict.items():
        if status == 'PASSED':
            pass_set.add(test_case)
        elif status == 'FAILED':
            fail_set.add(test_case)
        else:
            continue
    # step 3 parse all reports
    dirname_list, _ = my_os_walk(log_dir_parent)
    params_list = []
    for instance_id in dirname_list:
        test_output_path = os.path.join(log_dir_parent, instance_id, LOG_JSON_REPORT_OUTPUT)
        if not os.path.exists(test_output_path):
            continue
        params_list.append([instance_id, log_dir_parent, test_output_path, pass_set, fail_set])
    item_list = []
    for params in tqdm(params_list, ncols=70):
        item_list.append(gen_report(params))
    print('{}, Processed {} Report, SUCCESS {}, ERROR {}'.format(
        config.REPO_NAME, len(item_list),
        item_list.count(True), item_list.count(False)
    ))


def gen_report_file_parallel(repo_name_list_path: str, bug_mode: str):
    with open(repo_name_list_path, 'r') as f:
        repo_name_set = {line.strip() for line in f}
    config_list = get_all_config()
    filter_config_list = [[config, bug_mode] for config in config_list if config.REPO_NAME in repo_name_set]
    print(f'Total configs to process: {len(filter_config_list)}')
    random.shuffle(filter_config_list)
    # for config, bug_mode in filter_config_list:
    #     if config.REPO_NAME != 'grafana__worldmap_panel__91861ffa':
    #         continue
    #     gen_report_file([config, bug_mode])
    with Pool(64) as p:
        list(tqdm(p.imap(gen_report_file, filter_config_list), total=len(filter_config_list), ncols=70))


if __name__ == '__main__':
    repo_name_list_path = '/mnt/cfs_bj_mt/workspace/zengyucheng/workdir/workdir_for_swe_smith/zzz_rebuild_swe_smith/qianfan_coder_smith/controller/gt_all_repo_javascript.txt'
    gen_report_file_parallel(repo_name_list_path, 'single')
    print("finished.")
