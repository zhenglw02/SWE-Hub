import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from typing import Dict, Any
from tree_sitter import Language, Parser, Query, QueryCursor, Node
from utils_list.data_structure.base_data_structure import CodeEntity


class FilterManager:
    def __init__(self, language: Language, filter_queries: Dict[str, str]):
        self.language = language
        self.queries: Dict[str, Query] = self._compile_queries(filter_queries)

    def _compile_queries(self, filter_queries: Dict[str, str]) -> Dict[str, Query]:
        compiled_queries = {}
        for key, query_str in filter_queries.items():
            if query_str:
                try:
                    compiled_queries[key] = Query(self.language, query_str)
                except Exception as e:
                    print(f"Warning: Could not compile query for key '{key}'. Query: '{query_str}'. Error: {e}")
        return compiled_queries

    def _query_has_match(self, node: Node, query_key: str) -> bool:
        if not node or query_key not in self.queries:
            return False
        query = self.queries[query_key]
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(node)
        return len(captures) > 0

    def is_function(self, entity: CodeEntity) -> bool:
        return entity.code_type == 'function'

    def is_class(self, entity: CodeEntity) -> bool:
        return entity.code_type == 'class'
        
    def has_class_parents(self, entity: CodeEntity) -> bool:
        return entity.code_type == 'class' and self._query_has_match(entity.rel_src_node, "has_class_parents")

    def has_function_definitions(self, entity: CodeEntity) -> bool:
        return self._query_has_match(entity.rel_src_node, "has_function_definitions")

    def has_decorators(self, entity: CodeEntity) -> bool:
        parent = entity.src_node.parent
        if parent and parent.type == 'decorated_definition':
            return self._query_has_match(parent, "has_decorators")
        return False

    def has_if_else(self, entity: CodeEntity) -> bool:
        return self._query_has_match(entity.src_node, "has_if_else")

    def has_loops(self, entity: CodeEntity) -> bool:
        return self._query_has_match(entity.src_node, "has_loops")
        
    def has_indexing(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_indexing")

    def has_conditionals(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_conditionals")

    def has_function_calls(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_function_calls")

    def has_return_statements(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_return_statements")

    def has_exceptions(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_exceptions")

    def has_list_comprehensions(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_list_comprehensions")

    def has_imports(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_imports")

    def has_assignments(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_assignments")

    def has_lambda_functions(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_lambda_functions")

    def has_arithmetic_operations(self, entity: CodeEntity) -> bool:
        return self._query_has_match(entity.src_node, "has_arithmetic_operations")

    def has_wrappers(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_wrappers")

    def has_off_by_one_comparison(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_off_by_one_comparison")

    def has_binary_operations(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_binary_operations")

    def has_boolean_operations(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_boolean_operations")

    def has_unary_operations(self, entity: CodeEntity) -> bool: 
        return self._query_has_match(entity.src_node, "has_unary_operations") 

    def has_nested_class_definitions(self, entity: CodeEntity) -> bool:
        """
        Manually checks if a class contains nested class definitions.
        """
        # Ensure the entity is a class
        if not self.is_class(entity):
            return False

        # Capture all class definitions
        query = self.queries.get("has_nested_class_definitions")
        if not query:
            return False

        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(entity.src_node)

        # Check if any class is nested within the current class
        for _, node_list in captures.items():
            for node in node_list:
                # Ensure the nested class is not the same as the current class
                if node.id != entity.src_node.id:
                    return True  # Found a nested class
        return False
    
    def has_nested_function_definitions(self, entity: CodeEntity) -> bool:
        """
        Checks if the class or function has nested function definitions inside it.
        """
        # Ensure the entity is a function
        if not self.is_function(entity):
            return False

        # Capture all function definitions in the code
        query = self.queries.get("has_nested_function_definitions")
        if not query:
            return False

        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(entity.src_node)

        # Check if any function definition is inside another function's body
        for _, node_list in captures.items():
            for node in node_list:
                # Ensure the nested function is not the same as the current function
                if node.id != entity.src_node.id:
                    return True  # Found a nested function
        return False 

    def get_entity_filter_result(self, entity: CodeEntity) -> Dict[str, bool]:
        return {
            'is_function': self.is_function(entity),
            'is_class': self.is_class(entity),
            'has_function_definitions': self.has_function_definitions(entity),
            'has_class_parents': self.has_class_parents(entity),
            'has_decorators': self.has_decorators(entity),
            'has_if_else': self.has_if_else(entity),
            'has_loops': self.has_loops(entity),
            'has_indexing': self.has_indexing(entity),
            'has_conditionals': self.has_conditionals(entity),
            'has_function_calls': self.has_function_calls(entity),
            'has_return_statements': self.has_return_statements(entity),
            'has_exceptions': self.has_exceptions(entity),
            'has_list_comprehensions': self.has_list_comprehensions(entity),
            'has_imports': self.has_imports(entity),
            'has_assignments': self.has_assignments(entity),
            'has_lambda_functions': self.has_lambda_functions(entity),
            'has_arithmetic_operations': self.has_arithmetic_operations(entity),
            'has_wrappers': self.has_wrappers(entity),
            'has_off_by_one_comparison': self.has_off_by_one_comparison(entity),
            'has_binary_operations': self.has_binary_operations(entity),
            'has_boolean_operations': self.has_boolean_operations(entity),
            'has_unary_operations': self.has_unary_operations(entity),
            'has_nested_class_definitions': self.has_nested_class_definitions(entity),
            'has_nested_function_definitions': self.has_nested_function_definitions(entity),
        }