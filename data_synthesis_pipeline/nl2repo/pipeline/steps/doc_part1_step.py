"""Document Part 1 generation step - Project level documentation."""

import json
import os
import random
from multiprocessing import Pool
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

from nl2repo.pipeline.context import PipelineContext
from nl2repo.models.task import MetaInfo
from code_data_agent.model.agent import STOP_REASON_AGENT_STOP


def _process_cluster_worker(params: Tuple) -> Dict[str, Any]:
    """Worker function for processing a single cluster in a separate process.
    
    Args:
        params: Tuple of (cluster, meta_dict, output_path, max_iterations, llm_model, llm_base_url, llm_auth_token)
        
    Returns:
        Result dictionary with status and any errors
    """
    cluster, meta_dict, output_path, max_iterations, llm_model, llm_base_url, llm_auth_token = params
    cluster_id = cluster.get("id", "unknown")
    
    # Skip if already processed
    if os.path.exists(output_path + "__SUCCESS__"):
        return {"cluster_id": cluster_id, "status": "skipped", "error": None}
    
    try:
        # Import inside worker to avoid pickle issues
        from nl2repo.agents import DocPart1Agent
        from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
        from code_data_agent.sandbox.sandbox_k8s import SandboxK8s
        from nl2repo.config import get_settings
        
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
        safe_id = f"{meta_dict['repo']}_{cluster_id}".replace(".", "_").replace("__", "-").replace("_", "-").lower()
        random_suffix = random.randint(1000, 9999)
        pod_name = f"doc-part1-{safe_id}-{random_suffix}"
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
        
        try:
            # Create agent
            agent = DocPart1Agent(
                llm_server=llm_server,
                sandbox=sandbox,
                max_iterations=max_iterations,
            )
            
            # Generate documentation
            result = agent.generate_docs(
                instance=cluster,
                workdir_tree=meta_dict.get("workdir_tree", ""),
                local_workdir=meta_dict.get("local_repo_path", ""),
                kodo_workdir="/testbed",
            )
            
            # Save result (always save, including messages for debugging)
            output_data = {
                "id": cluster_id,
                "repo": meta_dict["repo"],
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
                return {"cluster_id": cluster_id, "status": "success", "error": None}
            else:
                return {"cluster_id": cluster_id, "status": result.get("status", "unknown"), "error": None}
                
        finally:
            sandbox.close()
            
    except Exception as e:
        import traceback
        return {
            "cluster_id": cluster_id,
            "status": "error",
            "error": f"DocPart1 cluster {cluster_id} failed: {e}\nTraceback:\n{traceback.format_exc()}"
        }


class DocPart1Step:
    """Generate project-level documentation using Doc Agent Part 1.
    
    This step:
    1. Loads cluster data from relationship analysis
    2. Runs DocPart1Agent for each cluster (in parallel)
    3. Saves generated documentation
    """
    
    def __init__(
        self,
        min_loc: int = 1000,
        max_iterations: int = 100,
        llm_model: str = "deepseek-v3.1-250821",
        llm_base_url: str = "",
        llm_auth_token: str = "",
        num_workers: int = 8,
    ):
        """Initialize Part 1 document generation step.
        
        Args:
            min_loc: Minimum lines of code threshold for cluster inclusion
            max_iterations: Maximum agent iterations per cluster
            llm_model: LLM model to use for generation
            num_workers: Number of parallel worker processes
        """
        self.min_loc = min_loc
        self.max_iterations = max_iterations
        self.llm_model = llm_model
        self.llm_base_url = llm_base_url
        self.llm_auth_token = llm_auth_token
        self.num_workers = num_workers
    
    def run(self, context: PipelineContext) -> None:
        """Execute Part 1 documentation generation.
        
        Args:
            context: Pipeline context with meta_list populated
        """
        context.log_progress("DocPart1", f"Generating Part 1 docs for {len(context.meta_list)} repos")
        
        # Create output directory
        output_dir = os.path.join(context.output_root, "step_5_document_part1")
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
                "workdir_tree": meta.workdir_tree or "",
                "local_repo_path": meta.local_repo_path or "",
            }
            
            repo_output_dir = os.path.join(output_dir, meta.repo)
            
            with open(cluster_path, "r") as f:
                for line in f:
                    cluster = json.loads(line)
                    
                    # Filter by LOC
                    if cluster.get("loc", 0) < self.min_loc:
                        continue
                    
                    cluster_id = cluster.get("id", "unknown")
                    output_path = os.path.join(repo_output_dir, f"{cluster_id}.json")
                    
                    tasks.append(
                        (
                            cluster,
                            meta_dict,
                            output_path,
                            self.max_iterations,
                            self.llm_model,
                            self.llm_base_url,
                            self.llm_auth_token,
                        )
                    )
        
        context.log_progress("DocPart1", f"Processing {len(tasks)} clusters with {self.num_workers} workers")
        
        if not tasks:
            context.log_progress("DocPart1", "No tasks to process")
            return
        
        # Process in parallel
        random.shuffle(tasks)  # Shuffle to distribute load
        
        with Pool(self.num_workers) as pool:
            results = list(tqdm(
                pool.imap_unordered(_process_cluster_worker, tasks),
                total=len(tasks),
                desc="Generating Part 1 docs",
                ncols=70,
            ))
        
        # Collect errors
        success_count = 0
        for result in results:
            if result["status"] == "success":
                success_count += 1
            elif result["error"]:
                context.add_error(result["error"])
        
        context.log_progress("DocPart1", f"Completed: {success_count}/{len(tasks)} successful")
