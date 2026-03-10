from dataclasses import dataclass
from typing import List, Dict, Any, Set, Optional


@dataclass
class CodeEntity:
    """Data class to hold information about a code entity (e.g. function, class)."""
    file_path: str
    full_content: str
    indent_level: int
    indent_size: int
    line_end: int
    line_start: int
    src_code: Any
    src_node: Any
    rel_src_node: Any
    complexity: int
    name: str
    code_type: str
    strip_body: str
    signature: str
    filter_results: dict
    file_extension: str
    hash_code: int
    qname: Optional[str] = None


class BugRewrite:
    hash_code: str = ""
    instance_id: str = ""
    cost: float = 0
    explanation: str = ""
    output: str
    rewrite: str
    strategy: str

    def __init__(
        self,
        hash_code: str,
        instance_id: str,
        rewrite: str,
        explanation: str,
        strategy: str,
        cost: float = 0,
        output: str = "",
    ):
        self.hash_code = hash_code
        self.instance_id = instance_id
        self.rewrite = rewrite
        self.explanation = explanation
        self.cost = cost
        self.strategy = strategy
        self.output = output

    def to_dict(self) -> dict[str, Any]:
        """Converts the bug rewrite to a dictionary."""
        return {
            "instance_id": self.instance_id,
            "hash_code": self.hash_code,
            "cost": self.cost,
            "explanation": self.explanation,
            "output": self.output,
            "rewrite": self.rewrite,
            "strategy": self.strategy,
        }