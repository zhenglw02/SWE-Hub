import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import ast
import random
from typing import Any
from pathlib import Path
from utils_list.data_structure.constants import FAIL_TO_PASS


def extract_pytest_test(
    base_path: Path, file_path: str | Path,
    test_name: str, class_name: str | None = None
) -> str | None:
    try:
        with open(base_path / file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return None

    # If class_name is provided, look inside the class
    if class_name:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for method in node.body:
                    if isinstance(method, ast.FunctionDef) and method.name == test_name:
                        return ast.unparse(method)  # Extract function from class
    else:
        # Look for a top-level function
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == test_name:
                return ast.unparse(node)  # Extract function

    return None


def get_test_function_python(instance: dict, idx: int, base_path: Path) -> dict[str, Any]:
    # test names are in pytest format (e.g., test_file::test_name)
    test = (
        random.choice(instance[FAIL_TO_PASS])
        if idx is None
        else instance[FAIL_TO_PASS][idx]
        if idx < len(instance[FAIL_TO_PASS])
        else instance[FAIL_TO_PASS][-1]
    )
    class_name = None
    if "::" not in test:
        test_file = "test.py"
        test_name = test.split()[0]
    else:
        test_file, test_name = test.split("::", 1)
        if "::" in test_name:
            class_name, test_name = test_name.split("::", 1)
        # Remove any parameters from the test name
        test_name = test_name.split("[")[0]

    # Clone repo for instance
    repo = instance["repo"]
    repo_name = repo.split("/")[-1]

    # Update test_file to be relative to the repo
    test_file = os.path.join(repo_name, test_file.replace('.', '/') + '.py')

    result = {
        "test_src": extract_pytest_test(base_path, test_file, test_name, class_name),
        "test_file": test_file,
        "test_name": test_name,
        "class_name": class_name,
        "repo_name": repo_name,
    }
    return result


def get_test_function_script(instance: dict, idx: int, base_path: Path) -> dict[str, Any]:
    # test names are in pytest format (e.g., test_file::test_name)
    test = (
        random.choice(instance[FAIL_TO_PASS])
        if idx is None
        else instance[FAIL_TO_PASS][idx]
        if idx < len(instance[FAIL_TO_PASS])
        else instance[FAIL_TO_PASS][-1]
    )
    class_name = None
    if "::" not in test:
        test_file = "test.py"
        test_name = test.split()[0]
    else:
        test_file, test_name = test.split("::", 1)
        if "::" in test_name:
            class_name, test_name = test_name.split("::", 1)
        # Remove any parameters from the test name
        test_name = test_name.split("[")[0]

    # Clone repo for instance
    repo = instance["repo"]
    repo_name = repo.split("/")[-1]

    # Update test_file to be relative to the repo
    test_file = os.path.join(base_path, repo_name, test_file)
    try:
        with open(test_file, "r", encoding="utf-8") as f:
            test_src = f.read()
    except Exception as e:
        test_src = None
    result = {
        "test_src": test_src,
        "test_file": test_file,
        "test_name": test_name,
        "class_name": class_name,
        "repo_name": repo_name,
    }
    return result