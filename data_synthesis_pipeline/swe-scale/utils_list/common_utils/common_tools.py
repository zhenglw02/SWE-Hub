
import os
import mmap
import orjson
import pickle
import hashlib
import simdjson
from typing import *
from tqdm import tqdm
from pathlib import Path


def dump_pkl(result_dict, path):
    with open(path, "wb") as tf:
        pickle.dump(result_dict, tf)


def load_pkl(path):
    new_dict = None
    with open(path, "rb") as tf:
        new_dict = pickle.load(tf)
    return new_dict


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


def generate_hash(s):
    return hashlib.sha256(s.encode()).hexdigest()[:8]


def load_unfinished_instances(
    dataset_path: os.PathLike | str,
    log_dir_issue_gen: os.PathLike | str,
    *,
    limit: int = 1000,
    show_progress: bool = True,   # 开启/关闭进度显示
) -> List[Dict[str, Any]]:
    try:
        _loads_full = orjson.loads
    except Exception:
        import json
        _loads_full = json.loads

    _PARSER = simdjson.Parser()
    dataset_path = Path(dataset_path)
    log_dir_issue_gen = Path(log_dir_issue_gen)

    datasets: List[Dict[str, Any]] = []
    total_lines = 0
    total_picked = 0
    total_finished = 0

    try:
        with open(dataset_path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm, \
                 tqdm(
                     total=mm.size(),
                     unit="B", unit_scale=True, unit_divisor=1024,
                     desc="scanning file",
                     ncols=80,
                     disable=not show_progress,
                 ) as p_file, \
                 tqdm(
                     total=limit,
                     desc="collected",
                     ncols=80,
                     disable=not show_progress,
                 ) as p_pick:

                size = mm.size()
                start = 0
                base_dir_str = str(log_dir_issue_gen)

                # 用最外层 memoryview 切片，循环内显式 release 子视图
                mv = memoryview(mm)
                try:
                    while start < size and len(datasets) < limit:
                        nl = mm.find(b"\n", start)
                        end = size if nl == -1 else nl

                        line_view = mv[start:end]
                        doc = None
                        try:
                            # 兼容 \r\n
                            if line_view and line_view[-1] == 13:  # b'\r'
                                line_view = line_view[:-1]

                            # ① 只解析 instance_id（零拷贝）
                            doc = _PARSER.parse(line_view)
                            try:
                                inst_id = doc["instance_id"]
                            except Exception:
                                inst_id = None

                            # ② 判断是否完成
                            if inst_id is not None:
                                succ_path = f"{base_dir_str}/{inst_id}/metadata.json__SUCCESS__"
                                finished = os.path.exists(succ_path)
                            else:
                                finished = False

                            # ③ 未完成才整行解析
                            if not finished:
                                obj = _loads_full(line_view)  # orjson 更快；无则回退 json
                                if isinstance(obj, dict):
                                    datasets.append(obj)
                                    total_picked += 1
                                    p_pick.update(1)
                            else:
                                total_finished += 1

                        finally:
                            # 释放对子缓冲区的引用，避免 BufferError
                            if isinstance(line_view, memoryview):
                                try:
                                    line_view.release()
                                except Exception:
                                    pass
                            line_view = None
                            doc = None

                        # ④ 更新字节进度
                        processed_bytes = (end - start) + (1 if nl != -1 else 0)
                        p_file.update(processed_bytes)

                        total_lines += 1
                        if show_progress and (total_lines % 100 == 0):
                            p_file.set_postfix(lines=total_lines, finished=total_finished, picked=total_picked)

                        # 下一行
                        start = end + 1 if nl != -1 else size
                finally:
                    try:
                        mv.release()
                    except Exception:
                        pass

    except (OSError, ValueError):
        # 回退：逐行读取（依然显示按字节的进度）
        file_size = os.path.getsize(dataset_path)
        with open(dataset_path, "rb") as f, \
             tqdm(
                 total=file_size,
                 unit="B", unit_scale=True, unit_divisor=1024,
                 desc="scanning file",
                 ncols=80,
                 disable=not show_progress,
             ) as p_file, \
             tqdm(
                 total=limit,
                 desc="collected",
                 ncols=80,
                 disable=not show_progress,
             ) as p_pick:

            base_dir_str = str(log_dir_issue_gen)
            for line in f:
                if len(datasets) >= limit:
                    break

                p_file.update(len(line))  # 按字节推进

                # 去掉换行与可能的 \r
                if line.endswith(b"\n"):
                    line = line[:-1]
                if line.endswith(b"\r"):
                    line = line[:-1]

                try:
                    doc = _PARSER.parse(line)
                    inst_id = doc["instance_id"]
                except Exception:
                    inst_id = None

                if inst_id is not None:
                    succ_path = f"{base_dir_str}/{inst_id}/metadata.json__SUCCESS__"
                    finished = os.path.exists(succ_path)
                else:
                    finished = False

                if not finished:
                    try:
                        obj = _loads_full(line)
                    except Exception:
                        obj = None
                    if isinstance(obj, dict):
                        datasets.append(obj)
                        total_picked += 1
                        p_pick.update(1)
                else:
                    total_finished += 1

                total_lines += 1
                if show_progress and (total_lines % 100 == 0):
                    p_file.set_postfix(lines=total_lines, finished=total_finished, picked=total_picked)
    return datasets