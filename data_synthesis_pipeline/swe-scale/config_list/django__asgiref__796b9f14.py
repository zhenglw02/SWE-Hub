
from pathlib import Path

class Config:
    # BASE REPOSITORY
    REPO_NAME = "django__asgiref__796b9f14"
    COMMIT = "796b9f14fd92d3131c7c39fab308ddd986d271eb"
    IMAGE_NAME = "iregistry.baidu-int.com/acg-airec/r2e_gym/my_swe_smith/swesmith.x86_64.django__asgiref.796b9f14:latest"
    LANGUAGE = "PYTHON"
    BASE_PATH = Path("./qianfan_coder_smith/config_list/repo_list")
    LOG_PATH = Path("./config_list/logs_config_list_1123")
    # LOG DIRS
    LOG_DIR = LOG_PATH / Path("logs_{}".format(REPO_NAME))
    ENV_IMAGE_BUILD_DIR = LOG_PATH / Path("logs_{}/build_images".format(REPO_NAME))
    INSTANCE_IMAGE_BUILD_DIR = LOG_PATH / Path("logs_{}/build_images/instances".format(REPO_NAME))
    LOG_DIR_RUN_EVALUATION = LOG_PATH / Path("logs_{}/run_evaluation".format(REPO_NAME))
    LOG_DIR_RUN_EVALUATION_COMBINE = LOG_PATH / Path("logs_{}/run_evaluation_combine".format(REPO_NAME))
    LOG_DIR_TASKS = LOG_PATH / Path("logs_{}/task_insts".format(REPO_NAME))
    LOG_DIR_BUG_GEN = LOG_PATH / Path("logs_{}/bug_gen".format(REPO_NAME))
    LOG_DIR_BUG_GEN_COMBINE = LOG_PATH / Path("logs_{}/bug_gen_combine".format(REPO_NAME))
    LOG_DIR_ISSUE_GEN = LOG_PATH / Path("logs_{}/issue_gen".format(REPO_NAME))

    # BACKEND PARAMS
    PYTEST_BACKEND = 'kodo'
    KUBECONFIG = '***'

    # INSTALLATION SPECS PARAMS
    ENV_NAME = "testbed"
    DOCKER_WORKDIR = "/testbed"
    PYTHON_VERSION = "3.12"
    FORCE_REBUILD = False
    REDO_EXISTING = False

    DEFAULT_SPECS = {
        # 仓库安装方法，不同的仓库配置方法不同
        "install": [
        ],
        "python": "3.12",
    }

    UBUNTU_VERSION = "22.04"
    CONDA_VERSION = "py312_24.1.2-0"
    GITHUB_TOKEN = "***"
    GITHUB_USERNAME = "***"
    ORG_NAME = "***"
    PROXY = "http://agent.baidu.com:8891"
    # 安装完仓库，记得将 docker images 推送到镜像仓库

    # Gen Bugs PARAMS
    SEED = 42
    PREFIX_METADATA = "metadata"
    PREFIX_BUG = "bug"
    CONTAINER_CONCURRENCY = 50
    WORKER_CONCURRENCY = 50

    # MAX BUGS FOR PROCEDURAL
    COMBINE_MAX_BUGS = 2000
    PROCEDURAL_MAX_BUGS = 2000

    # LLM GEN
    REWRITE_PER_BUGS_PER_ENTITY = 5 # 每个 candidate 最多可以rewrite次数
    MODIFY_PER_BUGS_PER_ENTITY = 5 # 每个 candidate 最多可以modify次数
    MODIFY_YAML = './stage_1_swe_smith/prompt_yaml_list/lm_modify.yml'
    PROMPT_KEYS = ["system", "demonstration", "instance"]
    REWRITE_YAML = './stage_1_swe_smith/prompt_yaml_list/lm_rewrite.yml'
    REWRITE_MAX_BUGS = 2000
    MODIFY_MAX_BUGS = 2000

    # LLM CONFIG
    BUG_GEN_MODEL_NAME = "openai/deepseek-v3"
    API_KEY = "***"
    API_BASE = "***"
    INPUT_COST_PER_TOKEN = 0.004
    OUTPUT_COST_PER_TOKEN = 0.016

    # COMBINE PARAMS
    # SAME FILE
    MAX_COMBOS = -1
    LIMIT_PER_FILE = 3 # 每个 patch 最多可以生成多少个组合
    NUM_PATCHES = 2

    # SAME MODULE
    LIMIT_PER_MODULE = 3
    DEPTH = 2

    # MAX BUGS FOR COLLECTIONS
    MAX_BUGS = 3000

    # EVALUATION PARAMS
    TIMEOUT = 600

    # PYTEST PARAMS
    PYTEST_TIMEOUT = 1200
    # 测试方法
    TEST_SCRIPT = 'pytest -n 10 --disable-warnings --color=no --tb=no --verbose -v --dist=loadscope'
    # 测试日志解析器
    PYTEST_LOG_PARSER = 'parse_log_pytest_xdist'
    RESOURCES = {"requests": {"cpu": "2", "memory": "5Gi"}}
    REDIRECT = True
    XML_REPORT = True

    # ISSUE GEN PARAMS
    SWE_BENCH_VERIFIED_PATH = "./princeton-nlp@SWE-bench_Verified"
    ISSUE_GEN_YAML = "./stage_4_gen_issue/issue_gen/ig_v2.yaml"
    ISSUE_GEN_MODEL_NAME = "openai/deepseek-v3.1-250821"
