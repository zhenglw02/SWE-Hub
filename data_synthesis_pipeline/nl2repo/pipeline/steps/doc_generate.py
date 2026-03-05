"""Document generation step - builds comprehensive documentation."""

import json
import os
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from nl2repo.pipeline.context import PipelineContext
from nl2repo.models.task import MetaInfo
from nl2repo.generators import TreeGenerator, build_full_doc


class DocGenerateStep:
    """Generates comprehensive documentation for repositories.
    
    This step:
    1. Generates project tree structures
    2. Assembles API documentation
    3. Creates usage examples
    4. Builds final documentation output
    """
    
    def __init__(
        self,
        min_loc: int = 1000,
        include_tree: bool = True,
    ):
        """Initialize document generation step.
        
        Args:
            min_loc: Minimum lines of code threshold for inclusion
            include_tree: Whether to include tree structure
        """
        self.min_loc = min_loc
        self.include_tree = include_tree
        self.tree_generator = TreeGenerator()
    
    def run(self, context: PipelineContext) -> None:
        """Execute document generation for all repos.
        
        Args:
            context: Pipeline context with meta_list populated
        """
        context.log_progress("DocGenerate", f"Generating docs for {len(context.meta_list)} repos")
        
        # First, update tree structures if needed
        if self.include_tree:
            self.update_tree_structures(context)
        
        # Generate documentation
        for meta in tqdm(context.meta_list, desc="Generating docs", ncols=70):
            try:
                self.generate_single(meta, context)
            except Exception as e:
                context.add_error(f"Doc generation failed for {meta.repo}: {e}")
    
    def update_tree_structures(self, context: PipelineContext) -> None:
        """Update tree structures for all repos.
        
        Args:
            context: Pipeline context
        """
        for meta in context.meta_list:
            if meta.local_repo_path and os.path.exists(meta.local_repo_path):
                meta.workdir_tree = self.tree_generator.generate_for_workdir(
                    meta.local_repo_path
                )
    
    def generate_single(
        self,
        meta: MetaInfo,
        context: PipelineContext,
    ) -> None:
        """Generate documentation for a single repository.
        
        Args:
            meta: Repository metadata
            context: Pipeline context
        """
        cluster_path = os.path.join(context.relationship_dir, f"{meta.repo}.jsonl")
        output_path = os.path.join(context.document_dir, f"{meta.repo}.jsonl")
        
        if not os.path.exists(cluster_path):
            context.add_error(f"No relationship data for {meta.repo}")
            return
        
        # Load part 1 documentation (project-level)
        part_1_doc = self.load_part_1_doc(meta, context)
        
        # Load function-level documentation
        function_pair_dict = self.load_function_docs(meta, context)
        
        # Process clusters
        with open(cluster_path, "r") as read_obj:
            with open(output_path, "w") as write_obj:
                for line in read_obj:
                    data = json.loads(line)
                    
                    # Filter by LOC
                    if data.get("loc", 0) < self.min_loc:
                        continue
                    
                    try:
                        result = self.build_doc_entry(
                            data, part_1_doc, function_pair_dict, meta
                        )
                        if result:
                            write_obj.write(json.dumps(result, ensure_ascii=False) + "\n")
                    except Exception as e:
                        continue
    
    def load_part_1_doc(
        self,
        meta: MetaInfo,
        context: PipelineContext,
    ) -> Dict[str, Dict[str, str]]:
        """Load project-level documentation.
        
        Args:
            meta: Repository metadata
            context: Pipeline context
            
        Returns:
            Dictionary mapping ID to documentation dict
        """
        # Note: This expects pre-generated documentation
        # Placeholder for integration with document generation pipeline
        return {}
    
    def load_function_docs(
        self,
        meta: MetaInfo,
        context: PipelineContext,
    ) -> Dict[str, Dict[str, Any]]:
        """Load function-level documentation.
        
        Args:
            meta: Repository metadata
            context: Pipeline context
            
        Returns:
            Dictionary mapping function path to documentation
        """
        # Note: This expects pre-generated documentation
        # Placeholder for integration with document generation pipeline
        return {}
    
    def build_doc_entry(
        self,
        data: Dict[str, Any],
        part_1_doc: Dict[str, Dict[str, str]],
        function_pair_dict: Dict[str, Dict[str, Any]],
        meta: MetaInfo,
    ) -> Optional[Dict[str, Any]]:
        """Build a single documentation entry.
        
        Args:
            data: Cluster data from relationship analysis
            part_1_doc: Project-level documentation
            function_pair_dict: Function-level documentation
            meta: Repository metadata
            
        Returns:
            Documentation entry dictionary or None
        """
        entities = data.get("entities", [])
        entities.sort(key=lambda x: f"{x.get('file_path', '')}::{x.get('qname', '')}")
        
        # Build entity pairs
        entity_pair_list = []
        for entity in entities:
            key = f"{entity.get('file_path', '')}::{entity.get('qname', '')}"
            if key in function_pair_dict:
                entity_pair_list.append((entity, function_pair_dict[key]))
        
        # Get project documentation
        instruct = part_1_doc.get(data.get("id", ""), {})
        
        # Build full documentation
        if entity_pair_list and instruct:
            full_prompt = build_full_doc(instruct, entity_pair_list, meta)
        else:
            # Minimal documentation without external docs
            full_prompt = self.build_minimal_doc(entities, meta)
        
        return {
            "repo": meta.repo,
            "image_name": meta.image_name,
            "id": data.get("id"),
            "type": data.get("type"),
            "patch": data.get("patch"),
            "complexity": data.get("complexity"),
            "loc": data.get("loc"),
            "entity_count": data.get("entity_count"),
            "full_prompt": full_prompt,
        }
    
    def build_minimal_doc(
        self,
        entities: List[Dict[str, Any]],
        meta: MetaInfo,
    ) -> str:
        """Build minimal documentation without external doc sources.
        
        Args:
            entities: List of entity dictionaries
            meta: Repository metadata
            
        Returns:
            Minimal documentation string
        """
        lines = [
            f"# {meta.repo}",
            "",
            "## Project Structure",
            "```",
            meta.workdir_tree or "N/A",
            "```",
            "",
            "## Code Entities",
            "",
        ]
        
        for entity in entities[:20]:  # Limit to first 20
            qname = entity.get("qname", entity.get("name", "Unknown"))
            lines.append(f"### {qname}")
            lines.append(f"- **File**: `{entity.get('file_path', '')}`")
            lines.append(f"- **Lines**: {entity.get('line_start', 0)}-{entity.get('line_end', 0)}")
            lines.append(f"- **Type**: {entity.get('code_type', '')}")
            
            if entity.get("signature"):
                lines.append(f"- **Signature**: `{entity['signature']}`")
            
            lines.append("")
        
        if len(entities) > 20:
            lines.append(f"... and {len(entities) - 20} more entities")
        
        return "\n".join(lines)