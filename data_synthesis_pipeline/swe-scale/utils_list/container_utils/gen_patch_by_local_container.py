import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import time
from tqdm.auto import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils_list.container_utils.container_pool_in_local import LocalContainerPool
from utils_list.container_utils.apply_patch_in_container_pool import (
    apply_change_and_get_patch_in_pool,
    apply_patches_with_pool
)


def gen_patch_parallel(item_list, repo_path, image_name, docker_workdir, worker_concurrency, container_concurrency) -> list[str]:
    start_time = time.time()
    total, successes, errors = 0, 0, 0
    total_tasks = len(item_list)
    desc = f"Apply bugs to gen patch, for {len(item_list)} candidates"
    patch_list = []
    with LocalContainerPool(image=image_name, workdir=docker_workdir, size=container_concurrency) as pool:
        with ThreadPoolExecutor(max_workers=worker_concurrency) as ex, \
            tqdm(total=total_tasks, desc=desc, unit="cand", leave=False) as pbar:
            futures = [
                ex.submit(
                    apply_change_and_get_patch_in_pool,
                    candidate=item['candidate'],
                    bug=item['bug'],
                    pool=pool,
                    host_repo_root=repo_path,
                    repo_workdir=docker_workdir,
                    reset_changes=True,
                )
                for item in item_list
            ]
            for fut in as_completed(futures):
                try:
                    patch = fut.result()
                    patch_list.append(patch)
                    if patch:
                        successes += 1
                    else:
                        errors += 1
                except Exception as e:
                    errors += 1
                    patch_list.append(None)
                    # 用 tqdm.write 避免破坏进度条
                    tqdm.write(f"[red]Error processing candidate[/red]: {e}")
                finally:
                    pbar.update(1)
                    pbar.set_postfix(ok=successes, err=errors)
        total += successes
    print(f"Apply {total} bugs. SUCCESS {successes}, FAIL {errors}, Cost time {round(time.time()-start_time, 1)} s")
    return patch_list


def apply_patches_parallel(all_combos, repo_path, image_name, docker_workdir, worker_concurrency, container_concurrency):
    start_time = time.time()
    successes, errors = 0, 0
    desc = f"Apply merged patch ({len(all_combos)} combos)"
    patch_list = []
    with LocalContainerPool(image=image_name, workdir=docker_workdir, size=container_concurrency) as pool:
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
                ) for combo, folder_path in all_combos
            }
            try:
                for fut in as_completed(future_to_cand):
                    try:
                        merged_patch = fut.result()
                        patch_list.append(merged_patch)
                        if merged_patch:
                            successes += 1
                        else:
                            errors += 1
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
    print(f"Apply {len(all_combos)} merged patch combos. SUCCESS {successes}, FAIL {errors}, Cost time {round(time.time()-start_time, 1)} s")
    return patch_list