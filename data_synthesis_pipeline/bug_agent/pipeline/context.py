"""Pipeline context for bug agent pipeline."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Shared context for pipeline execution."""

    input_path: str
    output_path: Optional[str]
    output_root: str
    report_root: str

    meta_list: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def ensure_directories(self) -> None:
        """ensure_directories."""
        os.makedirs(self.output_root, exist_ok=True)
        os.makedirs(self.report_root, exist_ok=True)

    def load_input_jsonl(self) -> List[Dict[str, Any]]:
        """load_input_jsonl."""
        self.meta_list = []
        with open(self.input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                self.meta_list.append(json.loads(line))
        return self.meta_list

    def save_output_jsonl(self) -> Optional[str]:
        """save_output_jsonl."""
        if not self.output_path:
            return None
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            for item in self.meta_list:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return self.output_path

    def add_error(self, error: str) -> None:
        """add_error."""
        self.errors.append(error)
        logger.error(error)

    def log_progress(self, step: str, message: str) -> None:
        """log_progress."""
        logger.info("[%s] %s", step, message)

    def get_report_dir(self, repo: str) -> str:
        """get_report_dir."""
        return os.path.join(self.report_root, repo)

    def get_bug_issue_output_dir(self) -> str:
        """get_bug_issue_output_dir."""
        return os.path.join(self.output_root, "step_1_bug_issue")

    def get_bug_issue_output_path(self, repo: str) -> str:
        """get_bug_issue_output_path."""
        safe_repo = repo.replace("/", "__")
        return os.path.join(self.get_bug_issue_output_dir(), f"{safe_repo}.json")
