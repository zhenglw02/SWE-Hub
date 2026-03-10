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
    LOG_XML_REPORT_OUTPUT
)
from utils_list.parser_utils.pytest_log_parsers import MAP_REPO_TO_PARSER
from stage_0_register_config.register_config import get_all_config, get_config



def gen_report(params):
    instance_id, log_dir_parent, test_output_path, pass_set, fail_set, log_parser = params
    if os.path.exists(str(log_dir_parent / instance_id / LOG_REPORT) + '__SUCCESS__'):
        return True
    try:
        passed_tests, failed_tests, _ = log_parser(test_output_path)
        if passed_tests is None or failed_tests is None:
            return
    except TimeoutError as e:
        return False
    if len(passed_tests) + len(failed_tests) == 0:    
        open(str(log_dir_parent / instance_id / LOG_REPORT) + '__SUCCESS__', "w")
        return False
    f2p, p2p, f2f, p2f = [], [], [], []
    for test_case in passed_tests:
        if test_case in pass_set:
            p2p.append(test_case)
        elif test_case in fail_set:
            f2p.append(test_case)
    for test_case in failed_tests:
        if test_case in pass_set:
            p2f.append(test_case)
        elif test_case in fail_set:
            f2f.append(test_case)
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


def gen_report_file(config, bug_mode):
    if bug_mode == 'single':
        log_dir_parent = config.LOG_DIR_RUN_EVALUATION
    else:
        log_dir_parent = config.LOG_DIR_RUN_EVALUATION_COMBINE
    # step 1 parse GROUND_TRUTH report
    ground_truth_path = str(Path(config.LOG_DIR) / (GROUND_TRUTH + '.json'))
    if not os.path.exists(ground_truth_path):
        return
    ground_truth_dict = json.load(open(ground_truth_path, 'r'))
    if len(ground_truth_dict) == 0:
        print(config.REPO_NAME, "ground truth error")
        return
    # step 2 parse F2P, P2P, F2F, P2F
    pass_set, fail_set = set(), set()
    for test_case, status in ground_truth_dict.items():
        if status == 'PASSED':
            pass_set.add(test_case)
        elif status == 'FAILED':
            fail_set.add(test_case)
        else:
            continue
    # step 3 parse all reports
    log_parser = MAP_REPO_TO_PARSER['parse_pytest_xml_report']
    dirname_list, _ = my_os_walk(log_dir_parent)
    params_list = []
    for instance_id in dirname_list:
        if instance_id.startswith(GROUND_TRUTH):
            continue
        test_output_path = os.path.join(log_dir_parent, instance_id, LOG_XML_REPORT_OUTPUT)
        if not os.path.exists(test_output_path):
            continue
        params_list.append([instance_id, log_dir_parent, test_output_path, pass_set, fail_set, log_parser])
    item_list = []
    for params in tqdm(params_list, ncols=70):
        item_list.append(gen_report(params))
    print('{}, Processed {} Report, SUCCESS {}, ERROR {}'.format(
        config.REPO_NAME, len(item_list),
        item_list.count(True), item_list.count(False)
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse log"
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
    gen_report_file(config, args.bug_mode)

