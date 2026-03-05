"""Entity filter management using tree-sitter queries.

Provides detection of various code patterns and structures within
parsed code entities.
"""

from typing import TYPE_CHECKING, Dict

from tree_sitter import Language, Query, QueryCursor, Node

if TYPE_CHECKING:
    from nl2repo.models.entity import CodeEntity


class FilterManager:
    """Manages tree-sitter queries for detecting code patterns.
    
    Provides methods to check for various code structures like loops,
    conditionals, decorators, etc. within a code entity.
    """
    
    def __init__(self, language: Language, filter_queries: Dict[str, str]):
        """Initialize filter manager with compiled queries.
        
        Args:
            language: tree-sitter Language for query compilation
            filter_queries: Dictionary mapping filter names to query strings
        """
        self.language = language
        self.queries: Dict[str, Query] = self._compile_queries(filter_queries)
    
    def _compile_queries(self, filter_queries: Dict[str, str]) -> Dict[str, Query]:
        """Compile query strings into tree-sitter Query objects.
        
        Args:
            filter_queries: Dictionary of filter name to query string
            
        Returns:
            Dictionary of filter name to compiled Query
        """
        compiled: Dict[str, Query] = {}
        for key, query_str in filter_queries.items():
            if query_str:
                try:
                    compiled[key] = Query(self.language, query_str)
                except Exception as e:
                    print(f"Warning: Could not compile query '{key}': {e}")
        return compiled
    
    def _query_has_match(self, node: Node, query_key: str) -> bool:
        """Check if a query matches any node in the subtree.
        
        Args:
            node: Root node to search from
            query_key: Name of the query to run
            
        Returns:
            True if query has at least one match
        """
        if not node or query_key not in self.queries:
            return False
        
        query = self.queries[query_key]
        cursor = QueryCursor(query)
        captures = cursor.captures(node)
        return len(captures) > 0
    
    # Basic type checks
    def is_function(self, entity: "CodeEntity") -> bool:
        """Check if entity is a function."""
        return entity.code_type == "function"
    
    def is_class(self, entity: "CodeEntity") -> bool:
        """Check if entity is a class."""
        return entity.code_type == "class"
    
    # Structure detection
    def has_class_parents(self, entity: "CodeEntity") -> bool:
        """Check if class has parent classes (inheritance)."""
        return (
            entity.code_type == "class"
            and self._query_has_match(entity.rel_src_node, "has_class_parents")
        )
    
    def has_function_definitions(self, entity: "CodeEntity") -> bool:
        """Check if entity contains function definitions."""
        return self._query_has_match(entity.rel_src_node, "has_function_definitions")
    
    def has_decorators(self, entity: "CodeEntity") -> bool:
        """Check if entity has decorators."""
        parent = entity.src_node.parent
        if parent and parent.type == "decorated_definition":
            return self._query_has_match(parent, "has_decorators")
        return False
    
    # Control flow detection
    def has_if_else(self, entity: "CodeEntity") -> bool:
        """Check for if/else statements."""
        return self._query_has_match(entity.src_node, "has_if_else")
    
    def has_loops(self, entity: "CodeEntity") -> bool:
        """Check for loop statements (for, while)."""
        return self._query_has_match(entity.src_node, "has_loops")
    
    def has_conditionals(self, entity: "CodeEntity") -> bool:
        """Check for conditional expressions."""
        return self._query_has_match(entity.src_node, "has_conditionals")
    
    # Expression detection
    def has_indexing(self, entity: "CodeEntity") -> bool:
        """Check for indexing operations."""
        return self._query_has_match(entity.src_node, "has_indexing")
    
    def has_function_calls(self, entity: "CodeEntity") -> bool:
        """Check for function calls."""
        return self._query_has_match(entity.src_node, "has_function_calls")
    
    def has_return_statements(self, entity: "CodeEntity") -> bool:
        """Check for return statements."""
        return self._query_has_match(entity.src_node, "has_return_statements")
    
    def has_exceptions(self, entity: "CodeEntity") -> bool:
        """Check for exception handling (try/except)."""
        return self._query_has_match(entity.src_node, "has_exceptions")
    
    def has_list_comprehensions(self, entity: "CodeEntity") -> bool:
        """Check for list comprehensions."""
        return self._query_has_match(entity.src_node, "has_list_comprehensions")
    
    def has_imports(self, entity: "CodeEntity") -> bool:
        """Check for import statements."""
        return self._query_has_match(entity.src_node, "has_imports")
    
    def has_assignments(self, entity: "CodeEntity") -> bool:
        """Check for assignment statements."""
        return self._query_has_match(entity.src_node, "has_assignments")
    
    def has_lambda_functions(self, entity: "CodeEntity") -> bool:
        """Check for lambda functions."""
        return self._query_has_match(entity.src_node, "has_lambda_functions")
    
    # Operator detection
    def has_arithmetic_operations(self, entity: "CodeEntity") -> bool:
        """Check for arithmetic operations."""
        return self._query_has_match(entity.src_node, "has_arithmetic_operations")
    
    def has_binary_operations(self, entity: "CodeEntity") -> bool:
        """Check for binary operations."""
        return self._query_has_match(entity.src_node, "has_binary_operations")
    
    def has_boolean_operations(self, entity: "CodeEntity") -> bool:
        """Check for boolean operations (and, or, not)."""
        return self._query_has_match(entity.src_node, "has_boolean_operations")
    
    def has_unary_operations(self, entity: "CodeEntity") -> bool:
        """Check for unary operations."""
        return self._query_has_match(entity.src_node, "has_unary_operations")
    
    # Special patterns
    def has_wrappers(self, entity: "CodeEntity") -> bool:
        """Check for wrapper patterns."""
        return self._query_has_match(entity.src_node, "has_wrappers")
    
    def has_off_by_one_comparison(self, entity: "CodeEntity") -> bool:
        """Check for potential off-by-one comparisons."""
        return self._query_has_match(entity.src_node, "has_off_by_one_comparison")
    
    def has_nested_class_definitions(self, entity: "CodeEntity") -> bool:
        """Check if class contains nested class definitions."""
        if not self.is_class(entity):
            return False
        
        query = self.queries.get("has_nested_class_definitions")
        if not query:
            return False
        
        cursor = QueryCursor(query)
        captures = cursor.captures(entity.src_node)
        
        # Check if any captured class is different from current class
        for _, node_list in captures.items():
            for node in node_list:
                if node.id != entity.src_node.id:
                    return True
        return False
    
    def has_nested_function_definitions(self, entity: "CodeEntity") -> bool:
        """Check if function contains nested function definitions."""
        if not self.is_function(entity):
            return False
        
        query = self.queries.get("has_nested_function_definitions")
        if not query:
            return False
        
        cursor = QueryCursor(query)
        captures = cursor.captures(entity.src_node)
        
        # Check if any captured function is different from current function
        for _, node_list in captures.items():
            for node in node_list:
                if node.id != entity.src_node.id:
                    return True
        return False
    
    def get_entity_filter_result(self, entity: "CodeEntity") -> Dict[str, bool]:
        """Run all filters on an entity and return results.
        
        Args:
            entity: Code entity to analyze
            
        Returns:
            Dictionary mapping filter names to boolean results
        """
        return {
            "is_function": self.is_function(entity),
            "is_class": self.is_class(entity),
            "has_function_definitions": self.has_function_definitions(entity),
            "has_class_parents": self.has_class_parents(entity),
            "has_decorators": self.has_decorators(entity),
            "has_if_else": self.has_if_else(entity),
            "has_loops": self.has_loops(entity),
            "has_indexing": self.has_indexing(entity),
            "has_conditionals": self.has_conditionals(entity),
            "has_function_calls": self.has_function_calls(entity),
            "has_return_statements": self.has_return_statements(entity),
            "has_exceptions": self.has_exceptions(entity),
            "has_list_comprehensions": self.has_list_comprehensions(entity),
            "has_imports": self.has_imports(entity),
            "has_assignments": self.has_assignments(entity),
            "has_lambda_functions": self.has_lambda_functions(entity),
            "has_arithmetic_operations": self.has_arithmetic_operations(entity),
            "has_wrappers": self.has_wrappers(entity),
            "has_off_by_one_comparison": self.has_off_by_one_comparison(entity),
            "has_binary_operations": self.has_binary_operations(entity),
            "has_boolean_operations": self.has_boolean_operations(entity),
            "has_unary_operations": self.has_unary_operations(entity),
            "has_nested_class_definitions": self.has_nested_class_definitions(entity),
            "has_nested_function_definitions": self.has_nested_function_definitions(entity),
        }