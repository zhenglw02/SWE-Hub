"""Document Part 2 generation step - Function level documentation."""

import json
import os
import random
from multiprocessing import Pool
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

from nl2repo.pipeline.context import PipelineContext
from nl2repo.models.task import MetaInfo
from code_data_agent.model.agent import STOP_REASON_AGENT_STOP


def _process_entity_worker(params: Tuple) -> Dict[str, Any]:
    """Worker function for processing a single entity in a separate process.
    
    Args:
        params: Tuple of (entity, meta_dict, output_path, max_iterations,
        llm_model, llm_base_url, llm_auth_token, dynamic_path)
        
    Returns:
        Result dictionary with status and any errors
    """
    entity, meta_dict, output_path, max_iterations, llm_model, llm_base_url, llm_auth_token, dynamic_path = params
    entity_qname = entity.get("qname", "unknown")
    
    # Skip if already processed
    if os.path.exists(output_path + "__SUCCESS__"):
        return {"entity": entity_qname, "status": "skipped", "error": None}
    
    try:
        # Import inside worker to avoid pickle issues
        from nl2repo.agents import DocPart2Agent
        from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
        from code_data_agent.tools.nl2repo_tools.tool_static_call_graph import (
            SimplePythonCallGraph,
        )
        from code_data_agent.sandbox.sandbox_k8s import SandboxK8s
        from nl2repo.config import get_settings
        
        # Load dynamic map if available
        dynamic_map = None
        if dynamic_path and os.path.exists(dynamic_path):
            try:
                with open(dynamic_path, "r") as f:
                    dynamic_map = json.load(f)
            except Exception:
                pass
        
        # Build static call graph
        local_workdir = meta_dict.get("local_repo_path", "")
        grapher = None
        if local_workdir and os.path.isdir(local_workdir):
            try:
                grapher = SimplePythonCallGraph(local_workdir)
            except Exception:
                pass
        
        # Create LLM server
        llm_server = LLMServerHTTP(
            base_url=llm_base_url,
            model=llm_model,
            headers={"Authorization": f"Bearer {llm_auth_token}"},
            timeout=600,
            max_retry=3,
        )
        
        # Create sandbox config
        settings = get_settings()
        # Generate unique pod name
        safe_id = f"{meta_dict['repo']}_{entity_qname}".replace(".", "_").replace("__", "-").replace("_", "-").lower()
        random_suffix = random.randint(1000, 9999)
        pod_name = f"doc-part2-{safe_id}-{random_suffix}"
        if len(pod_name) > 48:
            pod_name = f"{pod_name[:44]}-{random_suffix}"
        
        from code_data_agent.sandbox.scripts import (
            SCRIPT_BASH_FUNC,
            SCRIPT_SEARCH_FUNC,
        )
        sandbox = SandboxK8s(
            pod_name=pod_name,
            namespace=settings.k8s_namespace,
            kubeconfig_path=settings.kubeconfig_path,
            image=meta_dict["image_name"],
            enveriment=settings.get_container_environment(),
            cpu_request=settings.cpu_request,
            memory_request=settings.memory_request,
            workdir=settings.workdir,
            run_timeout=settings.coverage_timeout,
            scripts=[SCRIPT_BASH_FUNC, SCRIPT_SEARCH_FUNC],
        )
        
        kodo_workdir = "/testbed"
        
        try:
            # Create agent with optional call graph
            agent = DocPart2Agent(
                llm_server=llm_server,
                sandbox=sandbox,
                max_iterations=max_iterations,
                grapher=grapher,
                local_workdir=local_workdir,
                kodo_workdir=kodo_workdir,
            )
            
            # Generate documentation
            result = agent.generate_docs(
                entity=entity,
                dynamic_map=dynamic_map,
            )
            
            # Save result (always save, including messages for debugging)
            output_data = {
                "file_path": entity.get("file_path"),
                "qname": entity_qname,
                "status": result.get("status", "unknown"),
                "result_dict": result.get("result_dict", {}),
                "messages": result.get("messages", []),  # 保存完整对话记录
            }
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            if result.get("status") == STOP_REASON_AGENT_STOP:
                # Mark success only for agent_stop status
                open(output_path + "__SUCCESS__", "w").close()
                return {"entity": entity_qname, "status": "success", "error": None}
            else:
                return {"entity": entity_qname, "status": result.get("status", "unknown"), "error": None}
                
        finally:
            sandbox.close()
            
    except Exception as e:
        import traceback
        return {
            "entity": entity_qname,
            "status": "error",
            "error": f"DocPart2 entity {entity_qname} failed: {e}\nTraceback:\n{traceback.format_exc()}"
        }


class DocPart2Step:
    """Generate function-level documentation using Doc Agent Part 2.
    
    This step:
    1. Loads entity data from relationship analysis
    2. Runs DocPart2Agent for each entity (in parallel)
    3. Saves generated documentation
    """
    
    def __init__(
        self,
        min_complexity: int = 5,
        max_iterations: int = 50,
        llm_model: str = "deepseek-v3.1-250821",
        llm_base_url: str = "",
        llm_auth_token: str = "",
        num_workers: int = 8,
    ):
        """Initialize Part 2 document generation step.
        
        Args:
            min_complexity: Minimum complexity threshold for entity inclusion
            max_iterations: Maximum agent iterations per entity
            llm_model: LLM model to use for generation
            num_workers: Number of parallel worker processes
        """
        self.min_complexity = min_complexity
        self.max_iterations = max_iterations
        self.llm_model = llm_model
        self.llm_base_url = llm_base_url
        self.llm_auth_token = llm_auth_token
        self.num_workers = num_workers
    
    def run(self, context: PipelineContext) -> None:
        """Execute Part 2 documentation generation.
        
        Args:
            context: Pipeline context with meta_list populated
        """
        context.log_progress("DocPart2", f"Generating Part 2 docs for {len(context.meta_list)} repos")
        
        # Create output directory
        output_dir = os.path.join(context.output_root, "step_4_document")
        os.makedirs(output_dir, exist_ok=True)
        
        # Collect all tasks
        tasks = []
        for meta in context.meta_list:
            cluster_path = os.path.join(context.relationship_dir, f"{meta.repo}.jsonl")
            if not os.path.exists(cluster_path):
                context.add_error(f"No cluster data for {meta.repo}")
                continue
            
            # Convert meta to dict for pickling
            meta_dict = {
                "repo": meta.repo,
                "image_name": meta.image_name,
                "local_repo_path": meta.local_repo_path or "",
            }
            
            # Dynamic data path
            dynamic_path = os.path.join(context.relationship_dir, f"{meta.repo}.pkl")
            if not os.path.exists(dynamic_path):
                dynamic_path = None
            
            repo_output_dir = os.path.join(output_dir, meta.repo)
            
            # Collect unique entities from all clusters
            seen_entities = set()
            
            with open(cluster_path, "r") as f:
                for line in f:
                    cluster = json.loads(line)
                    for entity in cluster.get("entities", []):
                        entity_key = f"{entity['file_path']}::{entity['qname']}"
                        if entity_key in seen_entities:
                            continue
                        seen_entities.add(entity_key)

                        # Filter by complexity
                        complexity = entity.get("complexity", 1)
                        if complexity < self.min_complexity:
                            continue

                        # 只用 qname 作为文件名
                        qname = entity.get('qname', 'unknown')
                        safe_key = qname.replace(".", "_").replace("<", "").replace(">", "")
                        output_path = os.path.join(repo_output_dir, f"{safe_key}.json")
                        
                        tasks.append(
                            (
                                entity,
                                meta_dict,
                                output_path,
                                self.max_iterations,
                                self.llm_model,
                                self.llm_base_url,
                                self.llm_auth_token,
                                dynamic_path,
                            )
                        )
        
        context.log_progress("DocPart2", f"Processing {len(tasks)} entities with {self.num_workers} workers")
        
        if not tasks:
            context.log_progress("DocPart2", "No tasks to process")
            return
        
        # Process in parallel
        random.shuffle(tasks)  # Shuffle to distribute load
        
        with Pool(self.num_workers) as pool:
            results = list(tqdm(
                pool.imap_unordered(_process_entity_worker, tasks),
                total=len(tasks),
                desc="Generating Part 2 docs",
                ncols=70,
            ))
        
        # Collect errors
        success_count = 0
        for result in results:
            if result["status"] == "success":
                success_count += 1
            elif result["error"]:
                context.add_error(result["error"])
        
        context.log_progress("DocPart2", f"Completed: {success_count}/{len(tasks)} successful")
