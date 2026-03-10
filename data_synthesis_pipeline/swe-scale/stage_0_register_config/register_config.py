import os
import sys
import json
import inspect
import importlib
from types import SimpleNamespace
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

CONFIG_REGISTRY = {}


def is_config_module(module):
    """
    Checks if a module contains a 'Config' class.
    """
    return inspect.isclass(getattr(module, 'Config', None))


def register_configs_from_directory(input_dir, directory):
    """
    Dynamically imports Python modules from a directory, finds the 'Config' class,
    and registers it in the CONFIG_REGISTRY.
    """
    for filename in os.listdir(input_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3]
            module_path = f"{directory}.{module_name}"
            # try:
            module = importlib.import_module(module_path)
            if is_config_module(module):
                config_name = module_name
                CONFIG_REGISTRY[config_name] = module.Config
            # except (ImportError, AttributeError) as e:
            #     print(f"Could not import or register config from {module_path}: {e}")


def register_configs_from_directory_json(input_dir):
    filename_list = os.listdir(input_dir)
    for filename in filename_list:
        if not filename.endswith('.json'):
            continue
        json_dict = json.load(open(os.path.join(input_dir, filename), 'r'))
        obj = SimpleNamespace(**json_dict)
        CONFIG_REGISTRY[json_dict['REPO_NAME']] = obj
        ''


register_configs_from_directory('/mnt/cfs_bj_mt/workspace/zhengliwei/code/baidu/qianfan/code-data-agent-sdk/data_synthesis_pipeline/swe-smith/qianfan_coder_smith/config_list', 'config_list')
# register_configs_from_directory_json('/mnt/cfs_bj_mt/workspace/zengyucheng/workdir/workdir_for_swe_smith/zzz_rebuild_swe_smith/qianfan_coder_smith/config_list/config_list_1127_javascript')


def get_config(version: str):
    """
    Retrieves a configuration class from the registry based on its version.
    """
    if version not in CONFIG_REGISTRY:
        raise ValueError(f"Unknown config version: {version}")
    return CONFIG_REGISTRY[version]


def get_all_config():
    return CONFIG_REGISTRY.values()


# # Optional: Print the registered configurations for verification
if __name__ == "__main__":
    print("Registered Configurations:")
    for name in sorted(CONFIG_REGISTRY.keys()):
        print(f"- {name}")