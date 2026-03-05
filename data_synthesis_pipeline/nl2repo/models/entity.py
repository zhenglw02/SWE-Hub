"""Code entity models for representing parsed code structures."""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def generate_hash(s: str) -> str:
    """Generate a short hash for a string."""
    return hashlib.sha256(s.encode()).hexdigest()[:8]


@dataclass
class CodeEntity:
    """Represents a code entity (function, class, method) extracted from source code.
    
    This is the core data structure for representing parsed code elements,
    including their location, content, and metadata.
    """
    
    # File information
    file_path: str
    file_extension: str
    full_content: str
    
    # Location in file
    line_start: int
    line_end: int
    
    # Indentation
    indent_level: int
    indent_size: int
    
    # Source code
    src_code: str
    src_node: Any  # tree-sitter Node
    rel_src_node: Any  # Relative source node for analysis
    
    # Entity metadata
    name: str
    code_type: str  # 'function' or 'class'
    complexity: int
    hash_code: str
    
    # Derived content
    strip_body: Optional[str] = None
    signature: Optional[str] = None
    filter_results: Optional[Dict[str, bool]] = None
    
    # Hierarchy
    qname: Optional[str] = None  # Qualified name (e.g., ClassName.method_name)
    parent_name: Optional[str] = None  # Parent class name if method
    
    def to_json(self) -> Dict[str, Any]:
        """Convert entity to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "qname": self.qname,
            "parent_name": self.parent_name,
            "hash_code": self.hash_code,
            "code_type": self.code_type,
            "complexity": (self.line_end - self.line_start + 1) * self.complexity,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "src_code": self.src_code,
            "strip_body": self.strip_body,
            "signature": self.signature,
            "file_extension": self.file_extension,
        }
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "CodeEntity":
        """Create entity from JSON dictionary (partial reconstruction)."""
        return cls(
            file_path=data.get("file_path", ""),
            file_extension=data.get("file_extension", ""),
            full_content="",  # Not stored in JSON
            line_start=data.get("line_start", 0),
            line_end=data.get("line_end", 0),
            indent_level=0,
            indent_size=4,
            src_code=data.get("src_code", ""),
            src_node=None,
            rel_src_node=None,
            name=data.get("name", ""),
            code_type=data.get("code_type", "function"),
            complexity=data.get("complexity", 1),
            hash_code=data.get("hash_code", ""),
            strip_body=data.get("strip_body"),
            signature=data.get("signature"),
            qname=data.get("qname"),
            parent_name=data.get("parent_name"),
        )
    
    @property
    def loc(self) -> int:
        """Lines of code."""
        return self.line_end - self.line_start + 1
    
    @property
    def weighted_complexity(self) -> int:
        """Complexity weighted by lines of code."""
        return self.loc * self.complexity
    
    def __repr__(self) -> str:
        """__repr__."""
        return (
            f"CodeEntity({self.code_type}:{self.qname or self.name}"
            f"@{self.file_path}:{self.line_start}-{self.line_end})"
        )


@dataclass
class BugRewrite:
    """Represents a bug rewrite/fix suggestion."""
    
    hash_code: str
    instance_id: str
    rewrite: str
    explanation: str
    strategy: str
    cost: float = 0.0
    output: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "instance_id": self.instance_id,
            "hash_code": self.hash_code,
            "cost": self.cost,
            "explanation": self.explanation,
            "output": self.output,
            "rewrite": self.rewrite,
            "strategy": self.strategy,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BugRewrite":
        """Create from dictionary."""
        return cls(
            hash_code=data.get("hash_code", ""),
            instance_id=data.get("instance_id", ""),
            rewrite=data.get("rewrite", ""),
            explanation=data.get("explanation", ""),
            strategy=data.get("strategy", ""),
            cost=data.get("cost", 0.0),
            output=data.get("output", ""),
        )