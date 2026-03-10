import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import json
import random
import argparse
from pathlib import Path
from stage_0_register_config.register_config import get_config
from utils_list.common_utils.common_tools import search_files
from utils_list.data_structure.constants import KEY_INSTANCE_ID, KEY_PATCH, KEY_IMAGE_NAME
random.seed(42)


def main(config, bug_type):
    # bug_gen_path: str | Path, bug_type: str = "all", num_bugs: int = -1
    # from swesmith.constants import LOG_DIR_BUG_GEN, KEY_IMAGE_NAME, KEY_PATCH, PREFIX_BUG
    """
    Collect all the patches into a single json file that can be fed into swebench.harness.valid
    :param repo_path: Path to the bug_gen logs.
    :param bug_type: Type of patches to collect. (default: all)
    :param num_bugs: Number of bugs to collect. (default: all)
    """
    
    if os.path.exists(os.path.join(str(config.LOG_DIR), '{}__SUCCESS__'.format(bug_type))):
        return
    # get config variables
    log_dir_bug_gen = config.LOG_DIR_BUG_GEN
    prefix_bug = config.PREFIX_BUG
    log_dir_tasks = config.LOG_DIR_TASKS
    pytest_log_parser = config.PYTEST_LOG_PARSER
    os.makedirs(log_dir_tasks, exist_ok=True)
    # GET IMAGE NAME
    repo_name, commit = config.REPO_NAME, config.COMMIT
    image_name = config.IMAGE_NAME

    # FILTER BUG TYPE
    patches = []

    if bug_type == "single":
        prefix_list = ["llm__lm_rewrite", 'llm__lm_modify', 'procedural__']
    else:
        prefix_list = [bug_type + "_"]

    file_path_list = search_files(log_dir_bug_gen)
    for file_path in file_path_list:
        if not file_path.endswith(".diff"):
            continue
        flag = False
        for prefix in prefix_list:
            if prefix in os.path.basename(file_path):
                flag = True
                break
        if flag:
            # 这里需要改 not done
            # bug_type_and_uuid = file_path.split(f"{prefix_bug}__")[-1].split(".diff")[0]
            bug_type_and_uuid = os.path.basename(file_path).split(".diff")[0]
            instance_id = f"{repo_name}.{bug_type_and_uuid}"
            patch = {}
            # Add metadata if it exists
            metadata_file = f"metadata__{bug_type_and_uuid}.json"
            if os.path.exists(os.path.join(os.path.dirname(file_path), metadata_file)):
                patch.update(json.load(open(os.path.join(os.path.dirname(file_path), metadata_file))))

            # Add necessary bug patch information
            patch.update(
                {
                    KEY_INSTANCE_ID: instance_id,
                    KEY_PATCH: open(file_path, 'r').read(),
                    KEY_IMAGE_NAME: image_name,
                    "repo": repo_name,
                    "commit": commit,
                    'file_path': file_path,
                    'log_parser': pytest_log_parser
                }
            )
            patches.append(patch)
    random.shuffle(patches)
    if hasattr(config, "MAX_BUGS"):
        patches = patches[:config.MAX_BUGS]
    bug_patches_file = os.path.join(log_dir_tasks, f"{bug_type}_patches.json")
    if len(patches) > 0:
        with open(bug_patches_file, "w") as f:
            f.write(json.dumps(patches, indent=4))
        print(f"Saved {len(patches)} patches to {bug_patches_file}")
    else:
        print(f"No patches found for `{bug_type}` in {log_dir_bug_gen}")
    open(os.path.join(str(config.LOG_DIR), '{}__SUCCESS__'.format(bug_type)), 'w')


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Combine patches from the same files")
    parser.add_argument(
        "--config_name", type=str, help="parameters store path",
        default='1password__connect_sdk_python__463facf1'
    )
    parser.add_argument(
        "--bug_type",
        dest="bug_type",
        type=str,
        help="Type of patches to collect. (default: all)",
        default="single",
        choices=["single", "combine_file", "combine_module"]
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    main(config, args.bug_type)
    