"""Task and result models for pipeline operations."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TestCaseStatus(str, Enum):
    """Status of a test case execution."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class MetaInfo:
    """Metadata for a repository being processed."""
    
    repo: str
    image_name: str
    base_commit: str
    local_repo_path: Optional[str] = None
    coverage_path: Optional[str] = None
    workdir_tree: Optional[str] = None
    test_case_result: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "repo": self.repo,
            "image_name": self.image_name,
            "base_commit": self.base_commit,
            "local_repo_path": self.local_repo_path,
            "coverage_path": self.coverage_path,
            "workdir_tree": self.workdir_tree,
            "test_case_result": self.test_case_result,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetaInfo":
        """Create from dictionary."""
        return cls(
            repo=data.get("repo", ""),
            image_name=data.get("image_name", ""),
            base_commit=data.get("base_commit", ""),
            local_repo_path=data.get("local_repo_path"),
            coverage_path=data.get("coverage_path"),
            workdir_tree=data.get("workdir_tree"),
            test_case_result=data.get("test_case_result", {}),
        )


@dataclass
class CoverageTask:
    """Task definition for coverage collection."""
    
    repo: str
    image_name: str
    base_commit: str
    output_dir: str
    index: int = 0
    
    @property
    def repo_name(self) -> str:
        """Get sanitized repo name for pod naming."""
        return self.repo.replace("/", "-").replace("_", "-").lower()[:32]
    
    @property
    def instance_id(self) -> str:
        """Get instance identifier."""
        return f"ground_truth_{self.index:04d}"
    
    def to_ground_truth_dict(self) -> Dict[str, Any]:
        """Convert to ground truth format for compatibility."""
        return {
            "cost": 0,
            "explanation": None,
            "output": None,
            "rewrite": None,
            "strategy": None,
            "instance_id": "ground_truth",
            "patch": None,
            "image_name": self.image_name,
            "repo": self.repo,
            "commit": self.base_commit,
            "file_path": None,
        }


@dataclass
class CoverageResult:
    """Result of coverage collection."""
    
    task: CoverageTask
    success: bool
    coverage_path: Optional[str] = None
    xml_report_path: Optional[str] = None
    log_path: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class PatchTask:
    """Task definition for patch generation."""
    
    module_id: str
    entities: List[Any]  # List[CodeEntity]
    repo_path: str
    docker_workdir: str = "/testbed"
    
    @property
    def entity_count(self) -> int:
        """Number of entities in this task."""
        return len(self.entities)


@dataclass
class PatchResult:
    """Result of patch generation."""
    
    task: PatchTask
    success: bool
    patch_content: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class RelationshipResult:
    """Result of relationship analysis for a module/test case."""
    
    id: str
    type: str  # 'single' or 'module'
    test_cases: List[str]
    entities: List[Any]  # List[CodeEntity]
    patch: Optional[str] = None
    complexity: int = 0
    loc: int = 0
    entity_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "test_cases": self.test_cases,
            "entities": [e.to_json() if hasattr(e, 'to_json') else e for e in self.entities],
            "patch": self.patch,
            "complexity": self.complexity,
            "loc": self.loc,
            "entity_count": self.entity_count,
        }