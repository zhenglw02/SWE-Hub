import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import time
import json
import random
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from util_list.container_pool_in_local import LocalContainerPool
from util_list.apply_patch_in_container_pool import apply_patches_with_pool
from util_list.gen_bug_utils import get_combos
from util_list.common_utils import (
    get_image_name,
    generate_hash
)
from typing import *
from tqdm.auto import tqdm
from unidiff import PatchSet
from config.register_config import get_config
from config.constants import EXCLUDED_BUG_TYPES, COMBINE_MODULE


def my_os_walk(path, max_level=1):
    dir_list = []
    file_list = []
    count = 0
    for _, dir, file in os.walk(path):
        if count >= max_level:
            break
        else:
            dir_list.extend(dir)
            file_list.extend(file)
            count += 1
    return dir_list, file_list


def search_files(dir_path):
    result = []
    dir_list, file_list = my_os_walk(dir_path)
    for dir_name in dir_list:
        result.extend(search_files(os.path.join(dir_path, dir_name)))
    for file_path in file_list:
        result.append(os.path.join(dir_path, file_path))
    return result


def collection_file_by_depth(dir_path, depth, result):
    if depth == 1:
        result[dir_path] = search_files(dir_path)
    else:    
        dir_list, _ = my_os_walk(dir_path)
        for dirname in dir_list:
            collection_file_by_depth(os.path.join(dir_path, dirname), depth-1, result)


def main(config, filter_path):
    if os.path.exists(os.path.join(str(config.LOG_DIR), 'combine__SUCCESS__')):
        return
    bug_gen_dir = Path(config.LOG_DIR_BUG_GEN)
    max_combos = config.MAX_COMBOS
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

    # get filter patch path
    if filter_path is not None:
        filter_instance_path = set()
        with open(filter_path, 'r') as f:
            for line in tqdm(f, ncols=70, desc='loading raw path'):
                line = json.loads(line)
                filter_instance_path.add(line['meta']['raw_path'])
    else:
        filter_instance_path = None

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
            for p in combo:
                combos_count[p] -= 1
            all_combos.append([combo, Path(folder_path)])
    print(f"Found {len(all_combos)} merged patches, {len(map_path_to_patches)} modules at file depth {depth} with multiple patches, in {repo_name}.")
    
    # Try out all combinations of patches
    commit = config.COMMIT
    if hasattr(config, "REPO"):
        repo = config.REPO
    else:
        repo = config.REPO_NAME
    if hasattr(config, "IMAGE_NAME"):
        image_name = config.IMAGE_NAME
    else:
        image_name = get_image_name(repo, commit) + ':latest'
    docker_workdir = config.DOCKER_WORKDIR
    container_concurrency = config.CONTAINER_CONCURRENCY
    worker_concurrency = config.WORKER_CONCURRENCY
    worker_concurrency = min(worker_concurrency, container_concurrency, 64)
    container_concurrency = min(worker_concurrency, container_concurrency, 64)
    # container_concurrency = 1
    # worker_concurrency = 1
    start_time = time.time()
    successes, errors = 0, 0
    desc = f"Apply merged patch ({len(all_combos)} combos)"
    with LocalContainerPool(image=image_name, workdir=docker_workdir, size=container_concurrency) as pool:
        # === 串行处理 candidates（复用容器池） ===
        # for combo, folder_path in tqdm(all_combos[:200], ncols=70):
        #     merged_patch = apply_patches_with_pool(
        #         repo=".",
        #         patch_files=combo,
        #         pool=pool,
        #         repo_workdir=pool.workdir
        #     )
        #     if merged_patch is None:
        #         errors += 1
        #         continue
        #     successes += 1
        #     result = {
        #         "patch_files": [Path(f).name.rsplit(".", 1)[0] for f in combo],
        #         'patch_path': combo,
        #         "num_patch_files": len(combo),
        #     }
        #     file_name = f"{COMBINE_FILE}__{generate_hash(merged_patch)}"
        #     with open(folder_path / f"{prefix_bug}__{file_name}.diff", "w") as f:
        #         f.write(merged_patch)
        #     json.dump(result, open(folder_path / f"{prefix_metadata}__{file_name}.json", "w"), indent=4, ensure_ascii=False)
        #     open(folder_path / f"{prefix_metadata}__{file_name}.json__SUCCESS__", 'w')

        # === 并发处理 candidates（复用容器池） ===
        with ThreadPoolExecutor(max_workers=worker_concurrency) as ex, \
            tqdm(total=len(all_combos), desc=desc, unit="combo", leave=False) as pbar:
            future_to_cand = {
                ex.submit(
                    apply_patches_with_pool,
                    repo=".",
                    patch_files=combo,
                    pool=pool,
                    repo_workdir=pool.workdir
                ): (combo, folder_path)
                for combo, folder_path in all_combos
            }
            try:
                for fut in as_completed(future_to_cand):
                    combo, folder_path = future_to_cand[fut]
                    try:
                        merged_patch = fut.result()
                        if merged_patch is None:
                            errors += 1
                            continue
                        result = {
                            "patch_files": [Path(f).name.rsplit(".", 1)[0] for f in combo],
                            'patch_path': combo,
                            "num_patch_files": len(combo),
                        }
                        file_name = f"{COMBINE_MODULE}__{generate_hash(merged_patch)}"
                        with open(folder_path / f"{prefix_bug}__{file_name}.diff", "w") as f:
                            f.write(merged_patch)
                        json.dump(result, open(folder_path / f"{prefix_metadata}__{file_name}.json", "w"), indent=4, ensure_ascii=False)
                        open(folder_path / f"{prefix_metadata}__{file_name}.json__SUCCESS__", 'w')
                        successes += 1
                    except Exception as e:
                        errors += 1
                        # 用 tqdm.write 防止打乱进度条
                        tqdm.write(f"[red]Error processing combo[/red]: {e}")
                    finally:
                        pbar.update(1)
                        pbar.set_postfix(ok=successes, err=errors)
            except KeyboardInterrupt:
                # 支持 Ctrl-C：尝试取消剩余任务
                for f in future_to_cand:
                    f.cancel()
                raise
    print(f"Apply {len(all_combos)} merged patch combos for {repo_name}. SUCCESS {successes}, FAIL {errors}, Cost time {round(time.time()-start_time, 1)} s")
    open(os.path.join(str(config.LOG_DIR), 'samefile__SUCCESS__'), 'w')


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Combine patches from the same module")
    parser.add_argument(
        "--config_name", type=str, help="parameters store path", 
        # default='django__django_eaaf01c9'
    )
    parser.add_argument(
        "--filter_path", type=Path, help="Path to the dataset to evaluated patch.",
        # default="/mnt/cfs_bj_mt/workspace/zengyucheng/workdir/workdir_for_swe_smith/zzz_rebuild_swe_smith/repo_list/logs_django/export_insts/single_patches.jsonl"
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    main(config, args.filter_path)
