"""Pipeline context for env_agent pipeline."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Shared context for env_agent pipeline execution."""

    input_path: str
    output_root: str
    output_path: Optional[str] = None

    meta_list: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def ensure_directories(self) -> None:
        """Create output directories if they don't exist."""
        os.makedirs(self.output_root, exist_ok=True)

    def load_input_jsonl(self) -> List[Dict[str, Any]]:
        """Load JSONL input file into meta_list."""
        self.meta_list = []
        with open(self.input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                self.meta_list.append(json.loads(line))
        return self.meta_list

    def save_output_jsonl(self) -> Optional[str]:
        """Write meta_list back to output_path as JSONL."""
        if not self.output_path:
            return None
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            for item in self.meta_list:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return self.output_path

    def add_error(self, error: str) -> None:
        """Record an error and log it."""
        self.errors.append(error)
        logger.error(error)

    def log_progress(self, step: str, message: str) -> None:
        """Log a progress message."""
        logger.info("[%s] %s", step, message)

    def get_env_setup_output_dir(self) -> str:
        """Return the output directory for env_setup results."""
        return os.path.join(self.output_root, "step_1_env_setup")

    def get_env_setup_output_path(self, repo: str) -> str:
        """Return the per-repo JSON output path."""
        safe_repo = repo.replace("/", "__")
        return os.path.join(self.get_env_setup_output_dir(), f"{safe_repo}.json")

    def get_image_build_output_dir(self) -> str:
        """Return the output directory for image_builder results."""
        return os.path.join(self.output_root, "step_2_image_build")

    def get_image_build_output_path(self, repo: str) -> str:
        """Return the per-repo JSON output path for image_builder."""
        safe_repo = repo.replace("/", "__")
        return os.path.join(self.get_image_build_output_dir(), f"{safe_repo}.json")
