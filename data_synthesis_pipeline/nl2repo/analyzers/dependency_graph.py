"""Dependency graph construction and analysis using coverage data.

This module builds relationships between test cases and code functions
based on code coverage data, enabling closure analysis and module clustering.
"""

import os
import json
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple, TYPE_CHECKING

import networkx as nx

try:
    import community.community_louvain as community_louvain
except ImportError:
    community_louvain = None

if TYPE_CHECKING:
    from nl2repo.models.entity import CodeEntity


def link_coverage_to_functions(
    file_line_index: Dict[str, Dict[int, str]],
    coverage_json_path: str,
    project_root: str,
) -> Tuple[Dict[str, Set[str]], nx.DiGraph]:
    """Link coverage data to function signatures.
    
    Parses coverage JSON and builds a dependency graph connecting
    test cases to the functions they execute.
    
    Args:
        file_line_index: Mapping of file paths to line-to-function maps
        coverage_json_path: Path to coverage.json file
        project_root: Root directory of the project
        
    Returns:
        Tuple of (dependency dict {test -> functions}, networkx DiGraph)
    """
    print(f"🔗 Loading coverage: {coverage_json_path}")
    
    with open(coverage_json_path, "r") as f:
        cov_data = json.load(f)
    
    dependency_dict: Dict[str, Set[str]] = defaultdict(set)
    graph = nx.DiGraph()
    
    stats = {
        "matched_files": 0,
        "processed_lines": 0,
        "matched_functions": 0,
        "valid_contexts": 0,
    }
    
    files_map = cov_data.get("files", {})
    
    for relative_path, file_data in files_map.items():
        # Path alignment
        abs_path = os.path.abspath(os.path.join(project_root, relative_path))
        
        if abs_path not in file_line_index:
            continue
        
        stats["matched_files"] += 1
        line_to_func_map = file_line_index[abs_path]
        contexts = file_data.get("contexts", {})
        
        # Process line-to-test-case mapping
        for line_str, test_case_list in contexts.items():
            try:
                line_no = int(line_str)
            except ValueError:
                continue
            
            stats["processed_lines"] += 1
            
            # Find function for this line
            func_name = line_to_func_map.get(line_no)
            if not func_name:
                continue
            
            stats["matched_functions"] += 1
            func_signature = os.path.join(
                project_root, f"{relative_path}::{func_name}"
            )
            
            # Process test cases covering this line
            if not isinstance(test_case_list, list):
                continue
            
            for test_case in test_case_list:
                if not test_case or test_case == "":
                    continue
                
                stats["valid_contexts"] += 1
                
                # Build connection: Test -> Function
                dependency_dict[test_case].add(func_signature)
                
                # Add to graph
                graph.add_node(test_case, type="test")
                graph.add_node(func_signature, type="function", file=relative_path)
                graph.add_edge(test_case, func_signature)
    
    print(f"✅ Linking complete!")
    print(f"   - Matched files: {stats['matched_files']}")
    print(f"   - Processed lines: {stats['processed_lines']}")
    print(f"   - Matched functions: {stats['matched_functions']}")
    print(f"   - Valid connections: {stats['valid_contexts']}")
    
    return dependency_dict, graph


def analyze_modules(graph: nx.DiGraph) -> List[Dict[str, Any]]:
    """Analyze modules using community detection (Louvain algorithm).
    
    Args:
        graph: Dependency graph from link_coverage_to_functions
        
    Returns:
        List of module dictionaries with tests and functions
    """
    if community_louvain is None:
        print("Warning: python-louvain not installed, skipping module analysis")
        return []
    
    print("📦 Running module clustering (Community Detection)...")
    
    # Remove super-nodes (functions called by >60% of tests)
    total_tests = len([n for n, d in graph.nodes(data=True) if d.get("type") == "test"])
    threshold = total_tests * 0.6
    
    nodes_to_remove = []
    for node, data in graph.nodes(data=True):
        if data.get("type") == "function":
            in_degree = graph.in_degree(node)
            if in_degree > threshold:
                print(f"   ✂️ Removing common node: {node} ({in_degree} refs)")
                nodes_to_remove.append(node)
    
    # Create clustering view
    g_cluster = graph.copy()
    g_cluster.remove_nodes_from(nodes_to_remove)
    
    # Convert to undirected for Louvain
    ug = g_cluster.to_undirected()
    
    if ug.number_of_nodes() == 0:
        return []
    
    # Run Louvain algorithm
    print("   Running: Louvain Algorithm...")
    partition = community_louvain.best_partition(ug)
    
    # Organize results by cluster
    clusters: Dict[int, Dict[str, List[str]]] = {}
    
    for node, community_id in partition.items():
        if community_id not in clusters:
            clusters[community_id] = {"tests": [], "functions": []}
        
        node_type = graph.nodes[node].get("type")
        if not node_type:
            node_type = "test" if "test" in str(node) else "function"
        
        if node_type == "test":
            clusters[community_id]["tests"].append(node)
        else:
            clusters[community_id]["functions"].append(node)
    
    # Format output
    modules = []
    for cid, data in clusters.items():
        if len(data["tests"]) == 0:
            continue
        
        modules.append({
            "module_id": cid,
            "test_count": len(data["tests"]),
            "func_count": len(data["functions"]),
            "tests": sorted(data["tests"]),
            "functions": sorted(data["functions"]),
        })
    
    modules.sort(key=lambda x: x["test_count"], reverse=True)
    return modules


def analyze_closures(
    graph: nx.DiGraph,
) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]], Dict[str, List[str]]]:
    """Analyze closures from dependency graph.
    
    Provides three analysis modes:
    1. Test case closures (test -> functions)
    2. Module clustering (connected components)
    3. Function impact (function -> tests)
    
    Args:
        graph: Dependency graph
        
    Returns:
        Tuple of (test_case_closures, modules, func_impact)
    """
    print(f"📦 Analyzing closures (nodes: {graph.number_of_nodes()}, edges: {graph.number_of_edges()})...")
    
    # Mode 1: Test Case Closures
    print("   Running: Test case closure analysis...")
    test_case_closures: Dict[str, List[str]] = {}
    
    test_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "test"]
    
    for test_node in test_nodes:
        dependencies = sorted(list(graph.successors(test_node)))
        if dependencies:
            test_case_closures[test_node] = dependencies
    
    # Mode 2: Module Clustering
    print("   Running: Module clustering analysis...")
    modules = analyze_modules(graph)
    
    # Mode 3: Function Impact (reverse index)
    print("   Running: Function impact analysis...")
    func_impact: Dict[str, List[str]] = {}
    
    func_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "function"]
    
    for func_node in func_nodes:
        callers = sorted(list(graph.predecessors(func_node)))
        if callers:
            func_impact[func_node] = callers
    
    return test_case_closures, modules, func_impact


class CoverageProjection:
    """Flattened projection of coverage data for entity analysis.
    
    Provides mappings between test cases, function signatures,
    and CodeEntity objects for relationship analysis.
    """
    
    def __init__(
        self,
        dependency_dict: Dict[str, Set[str]],
        all_entities: List["CodeEntity"],
    ):
        """Initialize coverage projection.
        
        Args:
            dependency_dict: {test_case: {func_sig, ...}} from link_coverage_to_functions
            all_entities: List of CodeEntity objects
        """
        self.test_to_sigs = dependency_dict
        self.sig_to_tests: Dict[str, Set[str]] = defaultdict(set)
        self.sig_to_entity: Dict[str, "CodeEntity"] = {}
        
        # Build signature -> entity mapping
        for ent in all_entities:
            if ent.code_type != "function":
                continue
            sig = f"{ent.file_path}::{ent.qname}"
            self.sig_to_entity[sig] = ent
        
        # Build reverse index (function -> tests)
        for test_case, sigs in self.test_to_sigs.items():
            for sig in sigs:
                self.sig_to_tests[sig].add(test_case)
    
    def get_entity_object(self, signature: str) -> "CodeEntity":
        """Get CodeEntity by function signature."""
        return self.sig_to_entity.get(signature)
    
    def get_co_occurring_entities(self, target_sig: str) -> Set[str]:
        """Get function signatures that co-occur with target in same tests.
        
        This represents implicit coupling - functions tested together.
        
        Args:
            target_sig: Function signature to find co-occurrences for
            
        Returns:
            Set of co-occurring function signatures
        """
        related_tests = self.sig_to_tests.get(target_sig, set())
        co_entities: Set[str] = set()
        
        for test in related_tests:
            others = self.test_to_sigs.get(test, set())
            co_entities.update(others)
        
        co_entities.discard(target_sig)
        return co_entities


def analyze_entity_relations(
    dependency_dict: Dict[str, Set[str]],
    all_entities: List["CodeEntity"],
) -> Tuple[CoverageProjection, Dict[str, Dict[str, Any]]]:
    """Generate flattened projection of entity relationships.
    
    Args:
        dependency_dict: Test to function mappings
        all_entities: All extracted code entities
        
    Returns:
        Tuple of (CoverageProjection, flattened_view dict)
    """
    print("🕸️ Building entity projection (Entity-to-Entity)...")
    
    projection = CoverageProjection(dependency_dict, all_entities)
    flattened_view: Dict[str, Dict[str, Any]] = {}
    
    covered_signatures = projection.sig_to_tests.keys()
    
    for sig in covered_signatures:
        ent = projection.get_entity_object(sig)
        if not ent:
            continue
        
        tests = projection.sig_to_tests[sig]
        related_sigs = projection.get_co_occurring_entities(sig)
        
        flattened_view[sig] = {
            "file_path": ent.file_path,
            "func_name": ent.name,
            "qname": ent.qname,
            "covered_by_tests_count": len(tests),
            "related_entities_count": len(related_sigs),
            "related_entities": list(related_sigs),
        }
    
    print(f"✅ Projection complete! {len(flattened_view)} active entities.")
    return projection, flattened_view