"""
nl2repo - Code Repository to Natural Language Documentation Pipeline

This package provides tools for:
- Extracting code entities from repositories using tree-sitter
- Analyzing code dependencies via test coverage
- Generating structured documentation for code repositories
"""

__version__ = "0.1.0"

__all__ = [
    "config",
    "models",
    "parsers",
    "analyzers",
    "generators",
    "pipeline",
]
