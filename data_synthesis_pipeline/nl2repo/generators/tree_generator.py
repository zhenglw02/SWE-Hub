"""Project tree structure generation utilities."""

import os
from typing import Optional, Set

from nl2repo.config.defaults import DEFAULT_EXCLUDE_DIRS


def generate_tree_structure(
    start_path: str,
    exclude_dirs: Optional[Set[str]] = None,
    exclude_files: Optional[Set[str]] = None,
    max_depth: Optional[int] = None,
) -> str:
    """Generate a tree structure representation of a directory.
    
    Args:
        start_path: Root directory path
        exclude_dirs: Directory names to exclude
        exclude_files: File names to exclude
        max_depth: Maximum depth to traverse (None for unlimited)
        
    Returns:
        String representation of directory tree
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS
    if exclude_files is None:
        exclude_files = {".DS_Store", "Thumbs.db"}
    
    tree_lines: list[str] = []
    
    for root, dirs, files in os.walk(start_path):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        # Filter files
        files = [f for f in files if f not in exclude_files]
        
        # Calculate depth
        level = root.replace(start_path, "").count(os.sep)
        
        # Check max depth
        if max_depth is not None and level >= max_depth:
            dirs[:] = []  # Don't descend further
            continue
        
        # Build indentation
        indent = "│   " * level
        
        # Get directory name
        base_name = os.path.basename(root)
        if base_name == "":
            base_name = os.path.basename(start_path)
        
        # Add directory line
        tree_lines.append(f"{indent}{base_name}/")
        
        # Add file lines
        sub_indent = "│   " * (level + 1)
        for f in sorted(files):
            tree_lines.append(f"{sub_indent}{f}")
    
    return "\n".join(tree_lines)


class TreeGenerator:
    """Generator for project tree structures with configurable options."""
    
    def __init__(
        self,
        exclude_dirs: Optional[Set[str]] = None,
        exclude_files: Optional[Set[str]] = None,
        max_depth: Optional[int] = None,
    ):
        """Initialize tree generator.
        
        Args:
            exclude_dirs: Directory names to exclude
            exclude_files: File names to exclude
            max_depth: Maximum traversal depth
        """
        self.exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS
        self.exclude_files = exclude_files or {".DS_Store", "Thumbs.db"}
        self.max_depth = max_depth
    
    def generate(self, path: str) -> str:
        """Generate tree structure for a path.
        
        Args:
            path: Directory path
            
        Returns:
            Tree structure string
        """
        return generate_tree_structure(
            path,
            exclude_dirs=self.exclude_dirs,
            exclude_files=self.exclude_files,
            max_depth=self.max_depth,
        )
    
    def generate_for_workdir(
        self,
        local_path: str,
        workdir_name: str = "testbed",
    ) -> str:
        """Generate tree with path replaced for container workdir.
        
        Args:
            local_path: Local directory path
            workdir_name: Name to replace root with
            
        Returns:
            Tree structure with workdir paths
        """
        tree = self.generate(local_path)
        repo_name = os.path.basename(local_path.rstrip("/"))
        return tree.replace(repo_name, workdir_name)