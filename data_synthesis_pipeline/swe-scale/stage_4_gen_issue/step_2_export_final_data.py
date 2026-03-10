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
from stage_0_register_config.register_config import get_all_config, get_config


def export_data(config):
    log_dir_issue_gen = config.LOG_DIR_ISSUE_GEN
    log_dir_export_insts = os.path.join(str(config.LOG_DIR), 'export_insts')
    log_dir_export_insts_update = os.path.join(str(config.LOG_DIR), 'export_insts_update')
    os.makedirs(log_dir_export_insts_update, exist_ok=True)
    issue_dict = {}
    issue_path_list = set(search_files(log_dir_issue_gen))
    for issue_path in issue_path_list:
        if not issue_path.endswith('.json'):
            continue
        if issue_path + '__SUCCESS__' not in issue_path_list:
            continue
        json_dict = json.load(open(issue_path, 'r'))
        issue_dict[json_dict['instance_id']] = json_dict['responses']
    
    input_path_list = search_files(log_dir_export_insts)
    for input_path in input_path_list:
        if not input_path.endswith('.jsonl'):
            continue
        if input_path + '__SUCCESS__' not in input_path_list:
            continue
        output_path = input_path.replace(log_dir_export_insts, log_dir_export_insts_update)
        read_obj = open(input_path, 'r')
        write_obj = None
        for line in tqdm(read_obj, ncols=70):
            line = json.loads(line)
            problem_statement = issue_dict.get(line['instance_id'], None)
            if problem_statement is None:
                continue
            line['problem_statement'] = problem_statement
            line['meta']['test_output'] = ''
            if write_obj is None:
                write_obj = open(output_path, 'w')
            write_obj.write(json.dumps(line, ensure_ascii=False) + '\n')
        read_obj.close()
        if write_obj is not None:
            write_obj.close()
            open(output_path + '__SUCCESS__', 'w')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="export data"
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    export_data(config)


    
