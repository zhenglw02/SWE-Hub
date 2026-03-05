"""Code analysis and relationship extraction."""

from nl2repo.analyzers.dependency_graph import (
    link_coverage_to_functions,
    analyze_closures,
    analyze_modules,
    analyze_entity_relations,
    CoverageProjection,
)
from nl2repo.analyzers.closure_mapper import (
    map_closure_to_entities,
    filter_entity_by_rule,
    filter_result_by_test_case,
)

__all__ = [
    # Dependency graph
    "link_coverage_to_functions",
    "analyze_closures",
    "analyze_modules",
    "analyze_entity_relations",
    "CoverageProjection",
    # Closure mapping
    "map_closure_to_entities",
    "filter_entity_by_rule",
    "filter_result_by_test_case",
]