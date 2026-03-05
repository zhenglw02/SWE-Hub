"""Language configuration loading and management for tree-sitter parsing."""

from typing import Any, Dict, List, Optional, Set

import yaml
from tree_sitter import Language

# Tree-sitter language bindings
try:
    import tree_sitter_python as tspy
    import tree_sitter_javascript as tsjs
    import tree_sitter_typescript as tsts
except ImportError as e:
    raise ImportError(
        f"Missing tree-sitter language bindings: {e}. "
        "Install with: pip install tree-sitter-python tree-sitter-javascript tree-sitter-typescript"
    )


# Language name to tree-sitter Language mapping
LANGUAGE_MAP = {
    "python": lambda: Language(tspy.language()),
    "javascript": lambda: Language(tsjs.language()),
    "typescript": lambda: Language(tsts.language_typescript()),
    "tsx": lambda: Language(tsts.language_tsx()),
}


class LanguageConfig:
    """Configuration for a specific programming language.
    
    Holds tree-sitter queries and language-specific settings for
    code entity extraction and analysis.
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        """Initialize language configuration from parsed YAML data.
        
        Args:
            config_data: Dictionary containing language configuration
        """
        # Basic attributes
        self.name: str = config_data["name"]
        self.language: Language = self._get_tree_sitter_language(config_data["name"])
        self.placeholder_body: str = config_data["placeholder_body"]
        self.indent_size: int = config_data["indent_size"]
        self.file_extensions: Set[str] = set(config_data["file_extensions"])
        self.file_patterns: Set[str] = set(config_data["file_patterns"])
        
        # Query configurations
        queries = config_data["queries"]
        self.entity_query: str = queries["entity_query"]
        self.complexity_query: str = queries["complexity_query"]
        self.filter_queries: Dict[str, str] = queries["filters_query"]
        
        # Modifier queries (flattened from categories)
        self.modification_queries: Dict[str, str] = {}
        for category in queries.get("modifiers", {}).values():
            for key, value in category.items():
                self.modification_queries[key.upper()] = value
        
        # Language-specific syntax rules
        self.language_syntax = {
            "change_operators_groups": queries.get("change_operators_groups", []),
            "flipped_operators": queries.get("flipped_operators", {}),
            "change_constants_valid_parents": queries.get("change_constants_valid_parents", []),
            "function_context_types": queries.get("function_context_types", []),
            "shuffle_lines_blacklist": queries.get("shuffle_lines_blacklist", []),
        }
    
    def _get_tree_sitter_language(self, language_name: str) -> Language:
        """Get tree-sitter Language object for the given language name.
        
        Args:
            language_name: Name of the programming language
            
        Returns:
            tree-sitter Language object
            
        Raises:
            ValueError: If language is not supported
        """
        name_lower = language_name.lower()
        if name_lower not in LANGUAGE_MAP:
            supported = ", ".join(LANGUAGE_MAP.keys())
            raise ValueError(
                f"Unsupported language: {language_name}. "
                f"Supported languages: {supported}"
            )
        return LANGUAGE_MAP[name_lower]()
    
    def __repr__(self) -> str:
        """__repr__."""
        return f"LanguageConfig({self.name}, extensions={self.file_extensions})"


def load_language_config(yaml_path: str) -> LanguageConfig:
    """Load a single language configuration from a YAML file.
    
    Args:
        yaml_path: Path to the YAML configuration file
        
    Returns:
        LanguageConfig instance
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
    return LanguageConfig(config_data)


def get_all_language_configs(
    config_paths: Optional[List[str]] = None
) -> Dict[str, LanguageConfig]:
    """Load all language configurations from YAML files.
    
    Args:
        config_paths: List of paths to language config YAML files.
                     If None, uses default paths from settings.
                     
    Returns:
        Dictionary mapping language name (lowercase) to LanguageConfig
    """
    if config_paths is None:
        from nl2repo.config import get_settings
        config_paths = get_settings().language_config_paths
    
    config_map: Dict[str, LanguageConfig] = {}
    
    for yaml_path in config_paths:
        try:
            config = load_language_config(yaml_path)
            config_map[config.name.lower()] = config
            print(f"Loaded language config: {config.name}")
        except FileNotFoundError:
            print(f"Warning: Language config not found: {yaml_path}")
        except Exception as e:
            print(f"Warning: Failed to load {yaml_path}: {e}")
    
    return config_map