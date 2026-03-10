import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json
import time
import random
import argparse
from rich import print
from pathlib import Path
from tqdm.auto import tqdm
from collections import defaultdict
from multiprocessing import Pool
from utils_list.data_structure.base_data_structure import BugRewrite
from utils_list.procedural_operator.procedural_operation_modifier import (
    OperationChangeModifier,
    OperationFlipOperatorModifier,
    OperationSwapOperandsModifier,
    OperationBreakChainsModifier,
    OperationChangeConstantsModifier
)
from utils_list.procedural_operator.procedural_control_flow_modifier import (
    ControlIfElseInvertModifier,
    ControlIfElifInvertModifier,
    ControlShuffleLinesModifier,
)
from utils_list.procedural_operator.procedural_classes_modifier import (
    ClassRemoveBasesModifier,
    ClassShuffleMethodsModifier,
    ClassRemoveFuncsModifier,
)
from utils_list.procedural_operator.procedural_remove_modifier import (
    RemoveLoopModifier,
    RemoveConditionalModifier,
    RemoveAssignModifier,
    RemoveWrapperModifier,
    UnwrapWrapperModifier,
)
from utils_list.extract_utils.entity_procssor import extract_entities_from_directory
from utils_list.language_config.load_language_configs import get_all_language_config
from utils_list.container_utils.gen_patch_by_local_container import gen_patch_parallel
from stage_0_register_config.register_config import get_all_config, get_config


def init_modifier(language_config_dict):
    modifier_class_list = [
        # Operation
        (OperationChangeModifier,           0.4, 10, 100),
        (OperationFlipOperatorModifier,     0.4, 3, 100),
        (OperationSwapOperandsModifier,     0.4, 10, 100),
        (OperationBreakChainsModifier,      0.4, 10, 100),
        (OperationChangeConstantsModifier,  0.4, 10, 100),

        # Control
        (ControlIfElseInvertModifier,   0.25, 5, 100),
        (ControlIfElifInvertModifier,   0.25, 5, 100),
        (ControlShuffleLinesModifier,   0.25, 3, 10),

        # Classes
        (ClassRemoveBasesModifier,      0.25, 10, 100),
        (ClassShuffleMethodsModifier,   0.15, 10, 100),
        (ClassRemoveFuncsModifier,      0.25, 10, 100),

        # Removes
        (RemoveLoopModifier,        0.25, 10, 100),
        (RemoveConditionalModifier, 0.25, 10, 100),
        (RemoveAssignModifier,      0.25, 10, 100),
        (RemoveWrapperModifier,     0.25, 10, 100),
        (UnwrapWrapperModifier,     0.25, 10, 100),
    ]
    print('Init Modifier')
    modifier_map = defaultdict(list)
    for language_name, config in language_config_dict.items():
        for modifier_class, likelihood, \
            min_complexity_threshold, max_complexity_threshold in modifier_class_list:
            modifier = modifier_class(
                language_name=config.NAME,
                language=config.LANGUAGE,
                modification_querise=config.MODIFICATION_QUERIES,
                language_syntax_dict=config.LANGUAGE_SYNTAX_DICT,
                likelihood=likelihood,
                min_complexity_threshold=min_complexity_threshold,
                max_complexity_threshold=max_complexity_threshold,
            )
            for extension in config.FILE_EXTENSIONS:
                modifier_map[extension].append(modifier)
    return modifier_map


def procedural_gen_bugs(config):
    try:
        seed = config.SEED
        random.seed(seed)
        if os.path.exists(os.path.join(str(config.LOG_DIR), 'procedural__SUCCESS__')):
            return
        log_dir = Path(config.LOG_DIR_BUG_GEN)
        commit, repo_name, base_path = config.COMMIT, config.REPO_NAME, config.BASE_PATH
        prefix_metadata, prefix_bug = config.PREFIX_METADATA, config.PREFIX_BUG
        repo_path = os.path.join(base_path, repo_name)
        procedural_max_bugs = config.PROCEDURAL_MAX_BUGS
        assert procedural_max_bugs > 0, "PROCEDURAL_MAX_BUGS must be greater than 0"

        # step 1: extract entity
        try:
            language_config_dict = get_all_language_config()
            all_candidates = extract_entities_from_directory(
                directory_path=repo_path,
                language_config_dict=language_config_dict
            )
            print(f"{len(all_candidates)} candidates found in {repo_name}")
        except Exception as e:
            print(repo_path)
            return 

        if len(all_candidates) == 0:
            open(os.path.join(str(config.LOG_DIR), 'procedural__SUCCESS__'), 'w')
            return
        # step 2: init modifier
        modifiers_map = init_modifier(language_config_dict)
        # step 3: gen candidate entity
        filter_candidates = []
        for entity in all_candidates:
            modifiers = modifiers_map.get(entity.file_extension, [])
            for modifier in modifiers:
                if modifier.condition(entity):
                    filter_candidates.append([entity, modifier])
        print(f"Skip {len(all_candidates) * len(modifiers_map) - len(filter_candidates)} candidates, Left {len(filter_candidates)} candidates.")
        
        if len(filter_candidates) > procedural_max_bugs:
            random.shuffle(filter_candidates)
            filter_candidates = filter_candidates[: procedural_max_bugs]

        # step 4: gen modified code
        start_time = time.time()
        item_list = []
        for cand, modifier in filter_candidates:
            output_dir = []
            changed = False
            for _ in range(5):
                modified_code = modifier.apply(cand)
                if modified_code != cand.src_code:
                    changed = True
                    break
            if not changed:
                continue
            output_dir = (
                log_dir
                / cand.file_path.replace(repo_path, '').strip('/')
                / cand.name
            )
            a = f"procedural__{cand.hash_code.strip()}"
            bug = BugRewrite(
                instance_id= f"procedural__{modifier.name}__{cand.hash_code.strip()}",
                hash_code=cand.hash_code.strip(),
                rewrite=modified_code,
                explanation=modifier.explanation,
                cost=0.0,
                strategy=modifier.name,
                output=modified_code,
            )
            item_list.append({
                'candidate': cand,
                'bug': bug,
                'output_dir': output_dir,
                'type_name': 'procedural',
            })
        print(f"Generated {len(item_list)} bugs for {repo_name}. Cost 0 RMB. Cost time {round(time.time()-start_time, 1)} s")

        # apply bugs parallel in local container pool
        worker_concurrency = config.WORKER_CONCURRENCY    
        container_concurrency = config.CONTAINER_CONCURRENCY
        worker_concurrency = min(worker_concurrency, container_concurrency, 4)
        container_concurrency = min(worker_concurrency, container_concurrency, 4)
        patch_list = gen_patch_parallel(
            item_list=item_list,
            repo_path=repo_path,
            image_name=config.IMAGE_NAME,
            docker_workdir=config.DOCKER_WORKDIR,
            worker_concurrency=worker_concurrency,
            container_concurrency=container_concurrency,
        )
        assert len(patch_list) == len(item_list)
        for patch, item in tqdm(zip(patch_list, item_list), desc='writing patch'):
            if patch is None:
                continue
            candidate = item['candidate']
            bug = item['bug']
            instance_id = bug.instance_id
            output_dir = item['output_dir']
            type_name = item['type_name']
            output_dir.mkdir(parents=True, exist_ok=True)
            metadata_path = f"{prefix_metadata}__{instance_id}.json"
            bug_path = f"{prefix_bug}__{instance_id}.diff"
            success_path = os.path.join(output_dir / metadata_path) + '__SUCCESS__'
            with open(output_dir / metadata_path, "w") as f:
                json.dump(bug.to_dict(), f, indent=2)
            with open(output_dir / bug_path, "w") as f:
                f.write(patch)
            open(success_path, 'w').close()
        open(os.path.join(str(config.LOG_DIR), 'procedural__SUCCESS__'), 'w')
    except Exception as e:
        print('ERROR', e)
        return


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Generate bugs with procedural for a given repository name."
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    procedural_gen_bugs(config)
