import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import time
import yaml
import json
import random
import shutil
import jinja2
import litellm
import logging
import argparse
from typing import *
from rich import print
from pathlib import Path
from tqdm.auto import tqdm
from dotenv import load_dotenv
from litellm import completion
from multiprocessing import Pool
from itertools import combinations
from litellm.cost_calculator import completion_cost
from utils_list.data_structure.constants import EXCLUDED_BUG_TYPES, COMBINE_MODULE
from utils_list.data_structure.base_data_structure import BugRewrite, CodeEntity
from utils_list.language_config.load_language_configs import get_all_language_config
from utils_list.extract_utils.entity_procssor import extract_entities_from_directory
from utils_list.container_utils.gen_patch_by_local_container import apply_patches_parallel
from utils_list.common_utils.common_tools import search_files, my_os_walk, generate_hash
from stage_0_register_config.register_config import get_all_config, get_config


def is_same_source(combo, prefix_bug, prefix_metadata):
    hash_code_set = set()
    for patch_path in combo:
        meta_basename = os.path.basename(patch_path).replace(prefix_bug, prefix_metadata).replace('.diff', '.json')
        meta_path = os.path.join(os.path.dirname(patch_path), meta_basename)
        meta_dict = json.load(open(meta_path, 'r'))
        hash_code_set.add(meta_dict['hash_code'])
    if len(hash_code_set) == len(combo):
        return False
    else:
        return True

def get_combos(items, r, max_combos) -> list[tuple]:
    """Get `max_combos` combinations of items of length r or greater."""
    all_combos = []
    for new_combo in combinations(items, r):
        all_combos.append(new_combo)
        if max_combos != -1 and len(all_combos) >= max_combos:
            break
    random.shuffle(all_combos)
    return all_combos


def collection_file_by_depth(dir_path, depth, result):
    if depth == 1:
        result[dir_path] = search_files(dir_path)
    else:    
        dir_list, _ = my_os_walk(dir_path)
        for dirname in dir_list:
            collection_file_by_depth(os.path.join(dir_path, dirname), depth-1, result)


def combine_file(config):
    if os.path.exists(os.path.join(str(config.LOG_DIR), 'combine__SUCCESS__')):
        return
    filter_path = Path(config.LOG_DIR) / 'export_insts' / 'single.jsonl'
    if not os.path.exists(filter_path):
        return
    filter_instance_path = set()
    with open(filter_path, 'r') as f:
        for line in tqdm(f, ncols=70, desc='loading raw path'):
            line = json.loads(line)
            filter_instance_path.add(line['meta']['raw_path'])
    # if len(filter_instance_path) >= 50:
    #     return
    if len(filter_instance_path) < 20:
        open(os.path.join(str(config.LOG_DIR), 'combine__SUCCESS__'), 'w')
        return
    bug_gen_dir = str(config.LOG_DIR_BUG_GEN)
    bug_gen_dir_combine = str(config.LOG_DIR_BUG_GEN_COMBINE)
    max_combos = config.MAX_COMBOS
    combine_max_bugs = config.COMBINE_MAX_BUGS
    limit_per_module = config.LIMIT_PER_MODULE
    num_patches = config.NUM_PATCHES
    depth = config.DEPTH
    repo_name = config.REPO_NAME
    repo = repo_name
    prefix_bug = config.PREFIX_BUG
    prefix_metadata = config.PREFIX_METADATA
    seed = config.SEED
    random.seed(seed)
    
    # get patch by depth
    print(f"[{repo_name}] Extracting patch groups at depth {depth}")
    map_path_to_patches = {}
    collection_file_by_depth(bug_gen_dir, depth, map_path_to_patches)
    
    if map_path_to_patches == {}:
        print(f"[{repo}] No modules at file depth {depth} with multiple patches found")
        return
    print(
        f"[{repo}] Found {len(map_path_to_patches)} modules at file depth {depth} with multiple patches"
    )

    # get all combos
    combos_count = {}
    all_combos = []
    for folder_path, patch_files in tqdm(map_path_to_patches.items()):
        filter_patch_files = []
        for patch_file in patch_files:
            if not patch_file.endswith('.diff'):
                continue
            elif any(key in patch_file.lower() for key in EXCLUDED_BUG_TYPES):
                continue
            else:
                combos_count[patch_file] = limit_per_module
                filter_patch_files.append(patch_file)
        if len(filter_patch_files) <= 1:
            # Ignore if there is only one patch
            continue
        # Try out all combinations of patches
        combos = get_combos(filter_patch_files, num_patches, max_combos)
        random.shuffle(combos)
        for combo in combos:
            if any(combos_count[p] <= 0 for p in combo):
                continue
            if is_same_source(combo, prefix_bug, prefix_metadata):
                continue
            for p in combo:
                combos_count[p] -= 1
            all_combos.append([combo, Path(folder_path.replace(bug_gen_dir, bug_gen_dir_combine))])
    if combine_max_bugs > 0:
        random.shuffle(all_combos)
        all_combos = all_combos[:min(len(filter_instance_path) * 10, combine_max_bugs)]
    print(f"Found {len(all_combos)} merged patches, {len(map_path_to_patches)} modules at file depth {depth} with multiple patches, in {repo_name}.")

    # Try out all combinations of patches
    # apply bugs parallel in local container pool
    worker_concurrency, container_concurrency = 4, 4
    merged_patch_list = apply_patches_parallel(
        all_combos=all_combos,
        repo_path='.',
        image_name=config.IMAGE_NAME,
        docker_workdir=config.DOCKER_WORKDIR,
        worker_concurrency=worker_concurrency,
        container_concurrency=container_concurrency,
    )
    assert len(merged_patch_list) == len(all_combos)
    for merged_patch, (combo, output_dir) in zip(merged_patch_list, all_combos):
        if merged_patch is None:
            continue
        hash_code = generate_hash(merged_patch)
        result = {
            "instance_id": f"{COMBINE_MODULE}__{hash_code}",
            "hash_code": hash_code,
            "cost": 0,
            "strategy": COMBINE_MODULE,
            "patch_files": [Path(f).name.rsplit(".", 1)[0] for f in combo],
            'patch_path': combo,
            "num_patch_files": len(combo),
        }
        os.makedirs(output_dir, exist_ok=True)
        file_name = f"{COMBINE_MODULE}__{hash_code}"
        with open(output_dir / f"{prefix_bug}__{file_name}.diff", "w") as f:
            f.write(merged_patch)
        json.dump(result, open(output_dir / f"{prefix_metadata}__{file_name}.json", "w"), indent=4, ensure_ascii=False)
        open(output_dir / f"{prefix_metadata}__{file_name}.json__SUCCESS__", 'w')
    open(os.path.join(str(config.LOG_DIR), 'combine__SUCCESS__'), 'w')


def combine_file_parallel(repo_name_list_path):
    repo_name_set = set()
    with open(repo_name_list_path, 'r') as f:
        for line in f:
            repo_name_set.add(line.strip())
    config_list = get_all_config()
    filter_config_list = []
    for config in config_list:
        if config.REPO_NAME not in repo_name_set:
            continue
        filter_config_list.append(config)
    print('config size', len(filter_config_list))
    # for config in filter_config_list:
    #     combine_file(config)
    with Pool(32) as p:
        p.map(combine_file, filter_config_list)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="combine patch for a given repository name."
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    combine_file(config)
