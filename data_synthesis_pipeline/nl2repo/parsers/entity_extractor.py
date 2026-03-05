"""Code entity extraction using tree-sitter.

This module provides the core functionality for parsing source code
and extracting code entities (functions, classes, methods).
"""

import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from tree_sitter import Language, Node, Parser, Query, QueryCursor

from nl2repo.models.entity import CodeEntity, generate_hash
from nl2repo.parsers.filters import FilterManager
from nl2repo.parsers.language_config import LanguageConfig


class LanguageProcessor:
    """Processes source code files for a specific programming language.
    
    Uses tree-sitter to parse code and extract entities with their
    metadata, complexity metrics, and structural information.
    """
    
    def __init__(
        self,
        language: Language,
        entity_query_string: str,
        complexity_query_string: str,
        filter_queries: Dict[str, str],
        placeholder_body: str,
        indent_size: int,
        file_extensions: Set[str],
        file_patterns: Set[str],
        language_name: str,
    ):
        """Initialize language processor.
        
        Args:
            language: tree-sitter Language object
            entity_query_string: Query for finding entities (functions, classes)
            complexity_query_string: Query for calculating complexity
            filter_queries: Queries for various code pattern filters
            placeholder_body: Placeholder text for stripped function bodies
            indent_size: Default indentation size for this language
            file_extensions: File extensions for this language (e.g., {'.py'})
            file_patterns: Patterns to identify test files
            language_name: Human-readable language name
        """
        self.language = language
        self.parser = Parser(language)
        self.entity_query = Query(language, entity_query_string)
        self.complexity_query = Query(language, complexity_query_string)
        self.filter_queries = filter_queries
        self.filter_manager = FilterManager(language, filter_queries)
        self.placeholder_body = placeholder_body
        self.indent_size = indent_size
        self.file_extensions = file_extensions
        self.file_patterns = file_patterns
        self.language_name = language_name
    
    def get_file_extensions(self) -> Set[str]:
        """Get supported file extensions."""
        return self.file_extensions
    
    def get_test_file_patterns(self) -> Set[str]:
        """Get patterns for identifying test files."""
        return self.file_patterns
    
    def get_entity_from_node(
        self,
        node: Node,
        name: str,
        code_type: str,
        file_content: str,
        file_path: str,
        indent_size: int,
        file_extension: str,
    ) -> CodeEntity:
        """Convert a tree-sitter node to a CodeEntity.
        
        Args:
            node: tree-sitter Node representing the entity
            name: Name of the entity
            code_type: Type of entity ('function' or 'class')
            file_content: Full content of the source file
            file_path: Path to the source file
            indent_size: Indentation size to use
            file_extension: File extension
            
        Returns:
            CodeEntity instance
        """
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        source_code = node.text.decode("utf8")
        lines = file_content.splitlines()
        source_line = lines[start_line - 1]
        leading_whitespace = len(source_line) - len(source_line.lstrip())
        
        # Detect actual indent size from tabs
        effective_indent_size = indent_size
        if "\t" in source_line:
            guessed_size = source_line.expandtabs().find(source_line.lstrip())
            if guessed_size != -1:
                effective_indent_size = guessed_size
        
        indentation_level = (
            leading_whitespace // effective_indent_size
            if leading_whitespace > 0 and effective_indent_size > 0
            else 0
        )
        
        # Dedent source code
        code_lines = source_code.splitlines()
        if len(code_lines) > 1:
            dedented_source_code = [code_lines[0]]
            base_indent_str = " " * (indentation_level * effective_indent_size)
            base_indent_len = len(base_indent_str)
            
            for line in code_lines[1:]:
                if line.startswith(base_indent_str):
                    dedented_source_code.append(line[base_indent_len:])
                else:
                    dedented_source_code.append(line)
            source_code = "\n".join(dedented_source_code)
        else:
            source_code = code_lines[0] if code_lines else ""
        
        # Re-parse the dedented code
        parsed_tree = self.parser.parse(bytes(source_code, "utf8"))
        module_node = parsed_tree.root_node
        
        # Find relative source node
        rel_src_node = module_node
        if module_node.children:
            first_child = module_node.children[0]
            if first_child.type in [
                "function_definition",
                "class_definition",
                "decorated_definition",
            ]:
                rel_src_node = first_child
        
        return CodeEntity(
            file_path=file_path,
            full_content=file_content,
            indent_level=indentation_level,
            indent_size=effective_indent_size,
            line_end=end_line,
            line_start=start_line,
            src_code=source_code,
            src_node=node,
            rel_src_node=rel_src_node,
            complexity=1,
            name=name,
            code_type=code_type,
            strip_body=None,
            signature=None,
            filter_results=None,
            file_extension=file_extension,
            hash_code=generate_hash(source_code),
        )
    
    def extract_node_info(
        self, file_content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Extract node information from file content.
        
        Args:
            file_content: Source file content
            file_path: Path to source file
            
        Returns:
            List of dictionaries with node info (node, name, type)
        """
        try:
            tree = self.parser.parse(bytes(file_content, "utf8"))
            cursor = QueryCursor(self.entity_query)
            captures = cursor.captures(tree.root_node)
            
            info_map: Dict[int, Dict[str, Any]] = {}
            
            for capture_name, node_list in captures.items():
                for node in node_list:
                    if capture_name in ["entity.function", "entity.class"]:
                        def_node = node
                        if def_node.id not in info_map:
                            info_map[def_node.id] = {}
                        info_map[def_node.id]["node"] = def_node
                        info_map[def_node.id]["type"] = (
                            "function" if capture_name == "entity.function" else "class"
                        )
                    elif capture_name == "entity.name":
                        parent_def_node = node.parent
                        if parent_def_node:
                            if parent_def_node.id not in info_map:
                                info_map[parent_def_node.id] = {"node": parent_def_node}
                            info_map[parent_def_node.id]["name"] = node.text.decode("utf8")
            
            return [
                info
                for info in info_map.values()
                if "name" in info and "node" in info
            ]
            
        except Exception as e:
            print(f"Warning: Could not process '{file_path}': {e}", file=sys.stderr)
            return []
    
    def calculate_complexity(self, code_entity: CodeEntity) -> int:
        """Calculate cyclomatic complexity of a code entity.
        
        Args:
            code_entity: Entity to analyze
            
        Returns:
            Complexity score (1 + number of decision points)
        """
        node = code_entity.src_node
        complexity = 1
        
        if not node:
            return complexity
        
        try:
            cursor = QueryCursor(self.complexity_query)
            captures = cursor.captures(node)
            for _, node_list in captures.items():
                complexity += len(node_list)
            return complexity
        except Exception:
            return complexity
    
    def strip_function_body(
        self, entity: CodeEntity
    ) -> Optional[Tuple[str, str]]:
        """Strip function body, keeping signature and docstring.
        
        Args:
            entity: Function entity to process
            
        Returns:
            Tuple of (signature, stripped_body) or None if failed
        """
        try:
            function_node = entity.src_node
            body_node = function_node.child_by_field_name("body")
            
            if not body_node:
                print(f"Warning: No body found for '{entity.name}'")
                return None
            
            # Reconstruct signature from non-body children
            signature_parts = []
            for child in function_node.children:
                if child.id == body_node.id:
                    break
                signature_parts.append(child.text.decode("utf8"))
            
            signature_text = " ".join(signature_parts)
            signature_text = " ".join(signature_text.split())  # Normalize whitespace
            
            # Extract docstring if present
            docstring_text = ""
            if body_node.named_child_count > 0:
                first_child = body_node.named_children[0]
                if (
                    first_child.type == "expression_statement"
                    and first_child.child(0)
                    and first_child.child(0).type == "string"
                ):
                    docstring_text = first_child.text.decode("utf8")
            
            # Build stripped function
            indent_str = " " * self.indent_size
            final_parts = [signature_text]
            
            if docstring_text:
                final_parts.append(indent_str + docstring_text)
            
            final_parts.append(indent_str + self.placeholder_body)
            
            return signature_text, "\n".join(final_parts) + "\n"
            
        except Exception as e:
            print(f"Error stripping body for '{entity.name}': {e}")
            return None
    
    def resolve_hierarchy_and_overlap(
        self, entities: List[CodeEntity]
    ) -> Dict[int, str]:
        """Resolve entity hierarchy and build line-to-function mapping.
        
        Args:
            entities: List of all entities in a file
            
        Returns:
            Dictionary mapping line numbers to qualified function names
        """
        line_map: Dict[int, str] = {}
        classes = [e for e in entities if e.code_type == "class"]
        functions = [e for e in entities if e.code_type == "function"]
        
        # Assign qualified names based on class containment
        for func in functions:
            parent_class = None
            min_len = float("inf")
            
            for cls in classes:
                if cls.line_start <= func.line_start and cls.line_end >= func.line_end:
                    curr_len = cls.line_end - cls.line_start
                    if curr_len < min_len:
                        min_len = curr_len
                        parent_class = cls
            
            if parent_class:
                func.qname = f"{parent_class.name}.{func.name}"
                func.parent_name = parent_class.name
            else:
                func.qname = func.name
                func.parent_name = None
        
        # Build line map (larger ranges first, then smaller override)
        functions.sort(key=lambda x: (x.line_end - x.line_start), reverse=True)
        for func in functions:
            for line in range(func.line_start, func.line_end + 1):
                line_map[line] = func.qname
        
        return line_map
    
    def extract_entities(
        self, file_content: str, file_path: str, file_extension: str
    ) -> Tuple[List[CodeEntity], Dict[int, str]]:
        """Extract all entities from a source file.
        
        Args:
            file_content: Source file content
            file_path: Path to source file
            file_extension: File extension
            
        Returns:
            Tuple of (entities list, line-to-function map)
        """
        entities: List[CodeEntity] = []
        
        # Step 1: Extract nodes
        node_info_list = self.extract_node_info(file_content, file_path)
        if len(node_info_list) > 100:
            node_info_list = node_info_list[:100]
        
        # Step 2: Convert nodes to entities
        for node_info in node_info_list:
            try:
                node = node_info["node"]
                name = node_info["name"]
                code_type = node_info["type"]
                entity = self.get_entity_from_node(
                    node, name, code_type, file_content, file_path,
                    self.indent_size, file_extension
                )
                entities.append(entity)
            except KeyError:
                continue
        
        # Step 3: Calculate complexity
        for entity in entities:
            entity.complexity = self.calculate_complexity(entity)
        
        # Step 4: Strip function bodies
        for entity in entities:
            if entity.code_type != "function":
                continue
            result = self.strip_function_body(entity)
            if result:
                entity.signature, entity.strip_body = result
        
        # Step 5: Get filter results
        for entity in entities:
            entity.filter_results = self.filter_manager.get_entity_filter_result(entity)
        
        # Step 6: Resolve hierarchy and build line map
        line_to_function_map = self.resolve_hierarchy_and_overlap(entities)
        
        return entities, line_to_function_map


def init_all_processors(
    language_config_dict: Dict[str, LanguageConfig]
) -> Dict[str, LanguageProcessor]:
    """Initialize language processors from configurations.
    
    Args:
        language_config_dict: Dictionary of language configs
        
    Returns:
        Dictionary mapping file extensions to processors
    """
    processor_map: Dict[str, LanguageProcessor] = {}
    
    for language_name, config in language_config_dict.items():
        print(f"Initializing processor: {config.name}")
        processor = LanguageProcessor(
            language=config.language,
            entity_query_string=config.entity_query,
            complexity_query_string=config.complexity_query,
            filter_queries=config.filter_queries,
            placeholder_body=config.placeholder_body,
            indent_size=config.indent_size,
            file_extensions=config.file_extensions,
            file_patterns=config.file_patterns,
            language_name=config.name.lower(),
        )
        
        for extension in config.file_extensions:
            processor_map[extension] = processor
    
    return processor_map


def extract_entities_from_directory(
    directory_path: str,
    language_config_dict: Dict[str, LanguageConfig],
    exclude_tests: bool = True,
    max_entities: int = -1,
) -> Tuple[List[CodeEntity], Dict[str, Dict[int, str]]]:
    """Extract entities from all files in a directory.
    
    Args:
        directory_path: Root directory to scan
        language_config_dict: Language configurations
        exclude_tests: Whether to exclude test files
        max_entities: Maximum entities to extract (-1 for unlimited)
        
    Returns:
        Tuple of (all entities, file path to line map dictionary)
    """
    processor_map = init_all_processors(language_config_dict)
    all_entities: List[CodeEntity] = []
    file_path_line_map: Dict[str, Dict[int, str]] = {}
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            # Check extension and get processor
            _, file_extension = os.path.splitext(file)
            if not file_extension:
                continue
            
            processor = processor_map.get(file_extension)
            if processor is None:
                continue
            
            # Filter test files - use relative path to avoid matching output directory names
            if exclude_tests:
                test_patterns = processor.get_test_file_patterns()
                relative_root = os.path.relpath(root, directory_path)
                if any(
                    pattern in relative_root or pattern in file
                    for pattern in test_patterns
                ):
                    continue
            
            # Read file - use absolute path for consistent matching
            file_path = os.path.abspath(os.path.join(root, file))
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
            except Exception:
                continue
            
            # Extract entities
            entities_in_file, line_map = processor.extract_entities(
                file_content, file_path, file_extension
            )
            all_entities.extend(entities_in_file)
            file_path_line_map[file_path] = line_map
            
            if max_entities != -1 and len(all_entities) >= max_entities:
                return all_entities, file_path_line_map
    
    return all_entities, file_path_line_map