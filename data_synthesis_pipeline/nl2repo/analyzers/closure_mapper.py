"""Closure to entity mapping and filtering utilities.

Maps test closures to code entities and provides filtering
capabilities for entity selection.
"""

import os
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from nl2repo.config.defaults import DEFAULT_COMPLEXITY_THRESHOLD

if TYPE_CHECKING:
    from nl2repo.models.entity import CodeEntity


def filter_entity_by_rule(
    entities: List["CodeEntity"],
    threshold: int = DEFAULT_COMPLEXITY_THRESHOLD,
) -> List["CodeEntity"]:
    """Filter entities based on complexity and other rules.
    
    Applies filtering rules:
    - Only include functions (not classes)
    - Exclude dunder methods (__xxx__)
    - Exclude duplicates (by hash)
    - Exclude entities below complexity threshold
    
    Args:
        entities: List of CodeEntity objects to filter
        threshold: Minimum complexity threshold
        
    Returns:
        Filtered list of entities
    """
    hash_set: Set[str] = set()
    filtered: List["CodeEntity"] = []
    
    for entity in entities:
        # Only functions
        if entity.code_type != "function":
            continue
        
        # Skip dunder methods
        if entity.name.startswith("__"):
            continue
        
        # Skip duplicates
        if entity.hash_code in hash_set:
            continue
        
        # Check complexity threshold
        complexity = (entity.line_end - entity.line_start + 1) * entity.complexity
        if complexity < threshold:
            continue
        
        filtered.append(entity)
        hash_set.add(entity.hash_code)
    
    return filtered


def filter_result_by_test_case(
    test_case_result: Dict[str, str],
    test_case_list: List[str],
    entities: List["CodeEntity"],
    repo_path: str,
) -> Optional[Dict[str, Any]]:
    """Filter entities based on test case results.
    
    Validates that:
    - All test cases in test_case_list have PASSED
    - Entities are not test functions themselves
    
    Args:
        test_case_result: Dict mapping test case names to status
        test_case_list: List of test cases for this closure
        entities: Entities to filter
        repo_path: Repository root path
        
    Returns:
        Dictionary with filtered results, or None if invalid
    """
    # Normalize test case results for comparison
    reformat_test_case_result: Dict[str, str] = {}
    for key, value in test_case_result.items():
        new_key = (
            os.path.join(repo_path, key)
            .replace(".", "")
            .replace(":", "")
            .replace("/", "")
            .lower()
        )
        reformat_test_case_result[new_key] = value
    
    # Normalize test case list
    reformat_test_case_list: List[str] = []
    for test_case in test_case_list:
        normalized = (
            test_case
            .replace(".", "")
            .replace(":", "")
            .replace("/", "")
            .lower()
        )
        reformat_test_case_list.append(normalized)
    
    # Verify all test cases passed
    for test_case in reformat_test_case_list:
        result = [
            value == "PASSED"
            for key, value in reformat_test_case_result.items()
            if test_case in key
        ]
        if not all(result):
            return None
    
    # Filter out entities that are test functions
    filtered_entities: List["CodeEntity"] = []
    for entity in entities:
        name = (
            os.path.join(entity.file_path, entity.name)
            .replace(".", "")
            .replace(":", "")
            .replace("/", "")
            .lower()
        )
        if name in test_case_result:
            continue
        filtered_entities.append(entity)
    
    if len(filtered_entities) == 0:
        return None
    
    return {
        "id": "",
        "type": "",
        "test_cases": test_case_list,
        "entities": filtered_entities,
    }


def map_closure_to_entities(
    entity_class_map: Dict[str, List["CodeEntity"]],
    entity_func_map: Dict[str, "CodeEntity"],
    func_to_class_map: Dict[str, str],
    target_function_list: List[str],
) -> List["CodeEntity"]:
    """Map closure function signatures to CodeEntity objects.
    
    For each function in the closure, includes:
    - The function entity itself
    - All sibling methods if the function is a class method
    
    Args:
        entity_class_map: Map of class name to list of method entities
        entity_func_map: Map of function signature to entity
        func_to_class_map: Map of function signature to class name
        target_function_list: List of function signatures in closure
        
    Returns:
        List of CodeEntity objects in the closure
    """
    entity_list: List["CodeEntity"] = []
    
    # First pass: collect direct entity matches
    for target_function in target_function_list:
        if target_function not in entity_func_map:
            continue
        entity = entity_func_map[target_function]
        entity_list.append(entity)
    
    # Second pass: expand to include class siblings
    closure_entities: List["CodeEntity"] = []
    for entity in entity_list:
        key = f"{entity.file_path}::{entity.qname}"
        
        if key not in func_to_class_map:
            # Standalone function
            closure_entities.append(entity)
        else:
            # Class method - include all methods of the class
            class_name = func_to_class_map[key]
            class_methods = entity_class_map.get(class_name, [])
            closure_entities.extend(class_methods)
    
    return closure_entities


def build_entity_maps(
    entities: List["CodeEntity"],
) -> tuple[
    Dict[str, List["CodeEntity"]],
    Dict[str, "CodeEntity"],
    Dict[str, str],
]:
    """Build entity lookup maps from entity list.
    
    Args:
        entities: List of all CodeEntity objects
        
    Returns:
        Tuple of (entity_class_map, entity_func_map, func_to_class_map)
    """
    entity_class_map: Dict[str, List["CodeEntity"]] = {}
    entity_func_map: Dict[str, "CodeEntity"] = {}
    func_to_class_map: Dict[str, str] = {}
    
    for entity in entities:
        if entity.code_type == "function":
            # Build function signature key
            key = f"{entity.file_path}::{entity.qname}"
            entity_func_map[key] = entity
            
            # Track class membership
            class_name = entity.parent_name
            if class_name is not None:
                if class_name not in entity_class_map:
                    entity_class_map[class_name] = []
                entity_class_map[class_name].append(entity)
                func_to_class_map[key] = class_name
    
    return entity_class_map, entity_func_map, func_to_class_map