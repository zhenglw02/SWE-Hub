"""Test configuration helpers."""

import os
import sys


def _ensure_package_on_path():
    """Add the repository root to sys.path so imports work during tests."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


_ensure_package_on_path()
