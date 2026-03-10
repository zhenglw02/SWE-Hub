import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from tqdm.auto import tqdm
from datetime import datetime
from collections import defaultdict
from multiprocessing import Pool, cpu_count
from utils_list.common_utils.common_tools import search_files, my_os_walk
from utils_list.data_structure.constants import LOG_EVAL_SH, INSTANCE_PATH, LOG_TEST_OUTPUT
from stage_0_register_config.register_config import get_all_config, get_config


def gather(config, bug_mode):
    if bug_mode == 'single':
        log_dir_run_evaluation = config.LOG_DIR_RUN_EVALUATION
        log_dir_bug_gen = config.LOG_DIR_BUG_GEN
        output_path = os.path.join(str(config.LOG_DIR), 'export_insts', 'single.jsonl')
    else:
        log_dir_run_evaluation = config.LOG_DIR_RUN_EVALUATION_COMBINE
        log_dir_bug_gen = config.LOG_DIR_BUG_GEN_COMBINE
        output_path = os.path.join(str(config.LOG_DIR), 'export_insts', 'combine.jsonl')
    report_path_list = set(search_files(log_dir_run_evaluation))
    patch_path_list = set(search_files(log_dir_bug_gen))
    total_count, skip_count, left_count = 0, 0, 0
    patch_dict = {}
    for patch_path in tqdm(patch_path_list, ncols=70, desc='patching'):
        if not patch_path.endswith('.diff'):
            continue
        instance_id = os.path.basename(patch_path).split(".diff")[0]
        patch = open(patch_path, 'r').read()
        patch_dict[instance_id] = [patch, patch_path]

    os.makedirs(os.path.join(str(config.LOG_DIR), 'export_insts'), exist_ok=True)
    write_obj = open(output_path, 'w')
    eval_sh = None
    for report_path in tqdm(report_path_list, ncols=70, desc='reporting'):
        if os.path.basename(report_path) != 'report.json':
            continue
        if report_path + '__SUCCESS__' not in report_path_list:
            continue
        total_count += 1
        report_dict = json.load(open(report_path, 'r'))
        if len(report_dict['FAIL_TO_PASS']) == 0:
            skip_count += 1
            continue
        #  or len(report_dict["PASS_TO_PASS"]) == 0
        instance_id = os.path.basename(os.path.dirname(report_path)).split('.')[1]
        if eval_sh is None:
            try:
                eval_sh = open(os.path.join(os.path.dirname(report_path), LOG_EVAL_SH), 'r').read()
            except Exception as e:
                ''
        if eval_sh is None:
            continue
        left_count += 1
        test_output = open(os.path.join(os.path.dirname(report_path), LOG_TEST_OUTPUT), 'r').read()
        patch, patch_path = patch_dict[instance_id]
        result = {
            "instance_id": '{}.{}'.format(config.REPO_NAME, instance_id),
            "repo": config.REPO_NAME,
            "image_name": config.IMAGE_NAME,
            "base_commit": config.COMMIT,
            "patch": patch,
            "problem_statement": None,
            "FAIL_TO_PASS": report_dict["FAIL_TO_PASS"],
            "PASS_TO_PASS": report_dict["PASS_TO_PASS"],
            "eval_sh": eval_sh,
            "created_at": datetime.now().isoformat(),
            "version": None,
            'meta': {
                'test_output': test_output,
                'raw_path': patch_path,
                'log_parser': config.PYTEST_LOG_PARSER
            }
        }
        write_obj.write(json.dumps(result, ensure_ascii=False) + '\n')
    write_obj.close()
    open(output_path + '__SUCCESS__', 'w')
    print('REPO {}, TOTAL {}, SKIP {}, LEFT {}'.format(config.REPO_NAME, total_count, skip_count, left_count))
    return left_count


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
    gather(config, args.bug_mode)

