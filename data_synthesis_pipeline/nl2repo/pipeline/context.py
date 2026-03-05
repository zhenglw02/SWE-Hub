"""Pipeline context for managing state across steps."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nl2repo.models.task import MetaInfo

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Shared context for pipeline execution.
    
    Manages paths, state, and data flow between pipeline steps.
    """
    
    # Input configuration
    input_path: str
    output_root: str
    
    # Directory paths
    local_repo_dir: Optional[str] = None
    coverage_dir: Optional[str] = None
    meta_dir: Optional[str] = None
    relationship_dir: Optional[str] = None
    document_dir: Optional[str] = None
    
    # Runtime state
    meta_list: List[MetaInfo] = field(default_factory=list)
    current_meta: Optional[MetaInfo] = None
    
    # Results
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize directory paths if not set."""
        if self.local_repo_dir is None:
            self.local_repo_dir = os.path.join(self.output_root, "step_0_local_repo")
        if self.coverage_dir is None:
            self.coverage_dir = os.path.join(self.output_root, "step_1_coverage_report")
        if self.meta_dir is None:
            self.meta_dir = os.path.join(self.output_root, "step_2_meta_info")
        if self.relationship_dir is None:
            self.relationship_dir = os.path.join(self.output_root, "step_3_analysis_relationship")
        if self.document_dir is None:
            self.document_dir = os.path.join(self.output_root, "step_7_task")
    
    def ensure_directories(self) -> None:
        """Create all output directories."""
        for dir_path in [
            self.local_repo_dir,
            self.coverage_dir,
            self.meta_dir,
            self.relationship_dir,
            self.document_dir,
        ]:
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
    
    def load_input_meta(self) -> List[MetaInfo]:
        """Load metadata from input JSONL file.
        
        Returns:
            List of MetaInfo objects
        """
        self.meta_list = []
        
        with open(self.input_path, "r") as f:
            for line in f:
                data = json.loads(line)
                meta = MetaInfo.from_dict(data)
                self.meta_list.append(meta)
        
        return self.meta_list
    
    def save_meta_list(self, filename: str = "meta_info.jsonl") -> str:
        """Save current meta list to file.
        
        Args:
            filename: Output filename
            
        Returns:
            Path to saved file
        """
        output_path = os.path.join(self.meta_dir, filename)
        
        with open(output_path, "w") as f:
            for meta in self.meta_list:
                f.write(json.dumps(meta.to_dict(), ensure_ascii=False) + "\n")
        
        return output_path
    
    def get_repo_local_path(self, repo: str) -> str:
        """Get local path for a repository.
        
        Args:
            repo: Repository name
            
        Returns:
            Local directory path
        """
        return os.path.join(self.local_repo_dir, repo)
    
    def get_coverage_path(self, repo: str, index: int = 0) -> str:
        """Get coverage output path for a repository.
        
        Args:
            repo: Repository name
            index: Run index
            
        Returns:
            Path to coverage.json
        """
        return os.path.join(
            self.coverage_dir,
            repo,
            f"ground_truth_{index:04d}",
            "coverage.json",
        )
    
    def add_error(self, error: str) -> None:
        """Add an error message.
        
        Args:
            error: Error message
        """
        self.errors.append(error)
        logger.error(error)
    
    def log_progress(self, step: str, message: str) -> None:
        """Log progress message.
        
        Args:
            step: Step name
            message: Progress message
        """
        logger.info("[%s] %s", step, message)


def create_context_from_config(
    input_path: str,
    output_root: str,
) -> PipelineContext:
    """Create pipeline context from configuration.
    
    Args:
        input_path: Path to input JSONL file
        output_root: Root directory for outputs
        
    Returns:
        Initialized PipelineContext
    """
    context = PipelineContext(
        input_path=input_path,
        output_root=output_root,
    )
    context.ensure_directories()
    return context