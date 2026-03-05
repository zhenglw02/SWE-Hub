"""Relationship analysis step - analyzes code dependencies and generates patches."""

import json
import os
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from nl2repo.pipeline.context import PipelineContext
from nl2repo.models.task import MetaInfo, RelationshipResult
from nl2repo.parsers import get_all_language_configs, extract_entities_from_directory
from nl2repo.analyzers import (
    link_coverage_to_functions,
    analyze_closures,
    analyze_entity_relations,
    map_closure_to_entities,
    filter_entity_by_rule,
    filter_result_by_test_case,
)
from nl2repo.analyzers.closure_mapper import build_entity_maps
from nl2repo.generators import gen_module_patches_parallel


class RelationshipStep:
    """Analyzes code relationships and generates patches.
    
    This step:
    1. Extracts code entities using tree-sitter
    2. Links coverage data to functions
    3. Analyzes test closures and module clusters
    4. Generates patches for entity body replacements
    """
    
    def __init__(
        self,
        complexity_threshold: int = 10,
        worker_concurrency: int = 8,
        container_concurrency: int = 8,
    ):
        """Initialize relationship step.
        
        Args:
            complexity_threshold: Minimum complexity for entity inclusion
            worker_concurrency: Parallel workers for patch generation
            container_concurrency: Container pool size
        """
        self.complexity_threshold = complexity_threshold
        self.worker_concurrency = worker_concurrency
        self.container_concurrency = container_concurrency
        self._language_configs = None
    
    def run(self, context: PipelineContext) -> None:
        """Execute relationship analysis for all repos.
        
        Args:
            context: Pipeline context with meta_list populated
        """
        context.log_progress("Relationship", f"Analyzing {len(context.meta_list)} repos")
        
        # Load language configs once
        self._language_configs = get_all_language_configs()
        
        for meta in tqdm(context.meta_list, desc="Analyzing relationships", ncols=70):
            try:
                self.analyze_single(meta, context)
            except Exception as e:
                context.add_error(f"Relationship analysis failed for {meta.repo}: {e}")
    
    def analyze_single(
        self,
        meta: MetaInfo,
        context: PipelineContext,
    ) -> None:
        """Analyze relationships for a single repository.
        
        Args:
            meta: Repository metadata
            context: Pipeline context
        """
        repo_path = meta.local_repo_path
        coverage_path = meta.coverage_path
        output_path = os.path.join(context.relationship_dir, f"{meta.repo}.jsonl")
        dynamic_path = os.path.join(context.relationship_dir, f"{meta.repo}.pkl")
        
        # Check if already processed
        if os.path.exists(output_path + "__SUCCESS__"):
            return
        
        # Extract entities
        context.log_progress("Relationship", f"Extracting entities from {meta.repo}")
        entities, file_path_line_map = extract_entities_from_directory(
            directory_path=repo_path,
            language_config_dict=self._language_configs,
        )
        
        # Link coverage to functions
        dependency_dict, graph = link_coverage_to_functions(
            file_path_line_map, coverage_path, repo_path
        )
        
        # Analyze entity relations
        projection, flattened_view = analyze_entity_relations(dependency_dict, entities)
        
        # Analyze closures
        test_case_closures, modules, func_impact = analyze_closures(graph)
        
        # Build entity maps
        entity_class_map, entity_func_map, func_to_class_map = build_entity_maps(entities)
        
        # Process closures into results
        result_list: List[Dict[str, Any]] = []
        
        # Single test case closures
        for single_index, (test_case_name, tgt_function_list) in enumerate(test_case_closures.items()):
            closures_entities = map_closure_to_entities(
                entity_class_map, entity_func_map, func_to_class_map, tgt_function_list
            )
            filter_closures_entities = filter_entity_by_rule(
                closures_entities, threshold=self.complexity_threshold
            )
            
            if len(filter_closures_entities) == 0:
                continue
            
            result = filter_result_by_test_case(
                test_case_result=meta.test_case_result,
                test_case_list=[test_case_name],
                entities=filter_closures_entities,
                repo_path=repo_path,
            )
            
            if result is None:
                continue
            
            result["type"] = "single"
            result["id"] = f"single_{single_index:04d}"
            result_list.append(result)
        
        # Module closures
        for module_index, module in enumerate(modules):
            closures_entities = map_closure_to_entities(
                entity_class_map, entity_func_map, func_to_class_map, module["functions"]
            )
            filter_closures_entities = filter_entity_by_rule(
                closures_entities, threshold=self.complexity_threshold
            )
            
            result = filter_result_by_test_case(
                test_case_result=meta.test_case_result,
                test_case_list=module["tests"],
                entities=filter_closures_entities,
                repo_path=repo_path,
            )
            
            if result is None:
                continue
            
            result["type"] = "module"
            result["id"] = f"module_{module_index:04d}"
            result_list.append(result)
        
        # Generate patches
        context.log_progress("Relationship", f"Generating patches for {len(result_list)} closures")
        patch_dict = gen_module_patches_parallel(
            modules_data=result_list,
            repo_path=repo_path,
            image_name=meta.image_name,
            docker_workdir="/testbed",
            worker_concurrency=self.worker_concurrency,
            container_concurrency=self.container_concurrency,
        )
        
        # Write results
        with open(output_path, "w") as write_obj:
            for result in result_list:
                entities_json = [
                    entity.to_json() for entity in result["entities"]
                ]
                complexity = sum(e["complexity"] for e in entities_json)
                loc = sum(e["line_end"] - e["line_start"] + 1 for e in entities_json)
                
                result["entities"] = entities_json
                result["patch"] = patch_dict.get(result["id"])
                result["complexity"] = complexity
                result["loc"] = loc
                result["entity_count"] = len(entities_json)
                result["kodo_workdir"] = "/testbed"
                result["local_workdir"] = repo_path
                result["dynamic_path"] = dynamic_path
                result.update(meta.to_dict())
                
                write_obj.write(json.dumps(result, ensure_ascii=False) + "\n")
        
        # Mark success
        with open(output_path + "__SUCCESS__", "w") as f:
            f.write("")
        
        # Save dynamic data
        dynamic_result = {
            "dynamic_review": flattened_view,
            "function_to_tests": {k: list(v) for k, v in projection.sig_to_tests.items()},
            "test_to_functions": {k: list(v) for k, v in projection.test_to_sigs.items()},
        }
        with open(dynamic_path, "w") as f:
            json.dump(dynamic_result, f, ensure_ascii=False, indent=4)