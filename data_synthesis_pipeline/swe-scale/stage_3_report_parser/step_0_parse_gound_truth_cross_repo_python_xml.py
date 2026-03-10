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
from collections import defaultdict
from timeout_decorator import TimeoutError
from multiprocessing import Pool, cpu_count
from concurrent.futures import ThreadPoolExecutor
from utils_list.container_utils.pytest_test_in_container_pool import run_patch_in_container_pool
from utils_list.container_utils.container_single_in_kodo import KodoSingleUsePool
from utils_list.common_utils.common_tools import search_files, my_os_walk, load_pkl, dump_pkl
from utils_list.data_structure.constants import (
    GROUND_TRUTH, INSTANCE_PATH,
    LOG_TEST_OUTPUT, LOG_REPORT, 
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
    with open(test_output_path, 'r') as f:
        content = f.read()
    try:
        test_case_result_dict = log_parser(content)
    except TimeoutError as e:
        return False
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


def gen_report_file(config):
    log_dir_run_evaluation = Path(config.LOG_DIR_RUN_EVALUATION)
    output_path = str(Path(config.LOG_DIR) / (GROUND_TRUTH+ '.json'))
    # if os.path.exists(output_path + '__SUCCESS__'):
    #     return
    log_parser = MAP_REPO_TO_PARSER['parse_pytest_xml_report']
    dirname_list, _ = my_os_walk(log_dir_run_evaluation)
    test_case_status = defaultdict(list)
    for index in range(0, 10):
        test_output_path = os.path.join(
            str(log_dir_run_evaluation), 
            '{}{}'.format(GROUND_TRUTH, '_%.4d' % index),
            LOG_XML_REPORT_OUTPUT
        )
        if not os.path.exists(test_output_path):
            continue
        passed_tests, failed_tests, _ = log_parser(test_output_path)
        for test_case_name in passed_tests:
            test_case_status[test_case_name].append('PASSED')
        for test_case_name in failed_tests:
            test_case_status[test_case_name].append('FAILED')
    result_dict = {}
    for key, value_list in test_case_status.items():
        if 'FAILED' in value_list:
            result_dict[key] = "FAILED"
        elif all([value == 'PASSED' for value in value_list]):
            result_dict[key] = "PASSED"
        else:
            result_dict[key] = "SKIPPED"
    json.dump(result_dict, open(output_path, 'w'), indent=4, ensure_ascii=False)
    open(output_path + '__SUCCESS__', 'w')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse Log"
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    gen_report_file(config)
