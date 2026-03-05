"""Default constants and values for nl2repo pipeline."""

# Instance identifiers
GROUND_TRUTH = "ground_truth"
INSTANCE_PATH = "instance_path"

# Container defaults
DEFAULT_WORKDIR = "/testbed"
DEFAULT_TIMEOUT = 1200  # 20 minutes
DEFAULT_CPU_REQUEST = "2"
DEFAULT_MEMORY_REQUEST = "5Gi"

# Coverage command template
COVERAGE_COMMAND_TEMPLATE = """
pip install coverage -i https://pypi.org/simple
coverage run --rcfile={rcfile} -m pytest --junitxml={xml_path} > {log_path}
coverage json --rcfile={rcfile} -o {json_path}
"""

# Default environment variables for containers
DEFAULT_CONTAINER_ENV = {
    "PYTHONPATH": "/testbed",
    "PYTHONIOENCODING": "utf-8",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}

# File patterns for test detection
DEFAULT_TEST_PATTERNS = {
    "test_",
    "_test",
    "tests/",
    "test/",
    "spec/",
    "__tests__/",
}

# Exclude directories for code analysis
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "egg-info",
}

# Supported language file extensions
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

# Complexity threshold for entity filtering
DEFAULT_COMPLEXITY_THRESHOLD = 10