"""Patch generation for code entity modifications.

Generates git patches by applying entity body replacements in containers.
"""

import json
import shlex
import textwrap
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from tqdm.auto import tqdm

if TYPE_CHECKING:
    from nl2repo.models.entity import CodeEntity
    from nl2repo.generators.local_pool import LocalContainerPool


def to_container_path(
    candidate_file_path: str,
    host_repo_root: str,
    repo_workdir: str,
) -> str:
    """Convert host file path to container path.
    
    Args:
        candidate_file_path: Path to file (absolute or relative)
        host_repo_root: Host machine repository root
        repo_workdir: Container working directory
        
    Returns:
        Corresponding path inside container
        
    Raises:
        ValueError: If absolute path is not under host_repo_root
    """
    import os
    host_repo_root = os.path.normpath(host_repo_root)
    p = Path(candidate_file_path)
    
    if p.is_absolute():
        norm_p = os.path.normpath(str(p))
        common = os.path.commonpath([host_repo_root, norm_p])
        if common != host_repo_root:
            raise ValueError(
                f"file_path not under host_repo_root:\n"
                f"  file_path={p}\n"
                f"  host_repo_root={host_repo_root}"
            )
        rel = os.path.relpath(norm_p, host_repo_root)
        return str(Path(repo_workdir) / rel)
    else:
        return str(Path(repo_workdir) / candidate_file_path)


# Python script to run inside container for batch entity replacement
_BATCH_REPLACE_SCRIPT = """
import sys, json
from pathlib import Path
from collections import defaultdict

try:
    payload = json.load(sys.stdin)
except Exception as e:
    print(f"JSON load error: {e}", file=sys.stderr)
    sys.exit(1)

file_map = defaultdict(list)
for item in payload:
    file_map[item['file_path']].append(item)

for file_path, edits in file_map.items():
    p = Path(file_path)
    if not p.exists():
        print(f"Warning: File not found {file_path}", file=sys.stderr)
        continue

    try:
        original_lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        edits.sort(key=lambda x: x['start'], reverse=True)
        modified_lines = original_lines[:]
        
        for edit in edits:
            start_line = edit['start']
            end_line = edit['end']
            replacement = edit['replacement']
            
            idx_start = start_line - 1
            idx_end = end_line
            
            if idx_start < 0 or idx_end > len(modified_lines):
                continue
                
            repl_lines = replacement.splitlines(keepends=True)
            modified_lines[idx_start:idx_end] = repl_lines
            
        p.write_text("".join(modified_lines), encoding="utf-8")
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        sys.exit(1)
"""


def apply_batch_entities_in_pool(
    entities: List["CodeEntity"],
    *,
    pool: "LocalContainerPool",
    host_repo_root: str,
    repo_workdir: str = "/testbed",
) -> Optional[str]:
    """Apply entity body replacements and generate git patch.
    
    Args:
        entities: List of CodeEntity objects with strip_body set
        pool: Container pool for execution
        host_repo_root: Host repository root path
        repo_workdir: Container working directory
        
    Returns:
        Git patch content string, or None if no changes
    """
    if not entities:
        return None
    
    # Build change payload
    changes_payload = []
    for ent in entities:
        container_path = to_container_path(
            ent.file_path, host_repo_root, repo_workdir
        )
        replacement = ent.strip_body
        if replacement and not replacement.endswith("\n"):
            replacement += "\n"
        
        changes_payload.append({
            "file_path": container_path,
            "start": ent.line_start,
            "end": ent.line_end,
            "replacement": replacement,
        })
    
    json_payload = json.dumps(changes_payload)
    eof_token = f"EOF_{uuid.uuid4().hex}"
    
    # Cleanup commands
    cleanup_sh = textwrap.dedent("""
        git restore --staged . >/dev/null 2>&1 || true
        git reset --hard       >/dev/null 2>&1 || true
        git clean -fdx         >/dev/null 2>&1 || true
    """).strip()
    
    workdir_q = shlex.quote(repo_workdir)
    
    # Build shell script
    script = "\n".join([
        "set -eu",
        f"cd {workdir_q}",
        "",
        'if ! command -v git >/dev/null 2>&1; then echo "git not found" >&2; exit 127; fi',
        'PYBIN=$(command -v python3 || command -v python || true)',
        'git config --global --add safe.directory "$(pwd)" >/dev/null 2>&1 || true',
        
        # Reset repository
        "git restore --staged . >/dev/null 2>&1 || true",
        "git reset --hard       >/dev/null 2>&1 || true",
        "git clean -fdx         >/dev/null 2>&1 || true",
        
        # Cleanup trap
        "cleanup() {",
        cleanup_sh,
        "}",
        "trap cleanup EXIT",
        
        # Apply replacements via heredoc
        f"$PYBIN -c {shlex.quote(_BATCH_REPLACE_SCRIPT)} << '{eof_token}'",
        json_payload,
        eof_token,
        
        # Generate patch
        "git add -A",
        "git diff --staged -M -C --binary || true",
    ])
    
    # Execute
    try:
        with pool.lease() as name:
            proc = pool.exec_script(name, script, capture=True)
            patch = proc.stdout
            return patch if patch and patch.strip() else None
    except Exception as e:
        # Attempt cleanup on failure
        try:
            with pool.lease() as name2:
                pool.exec_script(
                    name2,
                    f"cd {workdir_q}; {cleanup_sh}",
                    capture=False,
                )
        except Exception:
            pass
        raise e


def gen_module_patches_parallel(
    modules_data: List[Dict[str, Any]],
    repo_path: str,
    image_name: str,
    docker_workdir: str,
    worker_concurrency: int = 10,
    container_concurrency: int = 5,
) -> Dict[str, str]:
    """Generate patches for multiple modules in parallel.
    
    Args:
        modules_data: List of module dicts with 'id' and 'entities' keys
        repo_path: Host repository path
        image_name: Docker image name
        docker_workdir: Container working directory
        worker_concurrency: Number of parallel workers
        container_concurrency: Number of containers in pool
        
    Returns:
        Dictionary mapping module ID to patch content
    """
    from nl2repo.generators.local_pool import LocalContainerPool
    
    start_time = time.time()
    results: Dict[str, str] = {}
    
    total_tasks = len(modules_data)
    desc = f"Generating patches for {total_tasks} modules"
    
    with LocalContainerPool(
        image=image_name,
        workdir=docker_workdir,
        size=container_concurrency,
    ) as pool:
        with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
            with tqdm(total=total_tasks, desc=desc) as pbar:
                # Submit tasks
                future_to_mid = {}
                for mod in modules_data:
                    mid = mod["id"]
                    entities = mod["entities"]
                    
                    fut = executor.submit(
                        apply_batch_entities_in_pool,
                        entities=entities,
                        pool=pool,
                        host_repo_root=repo_path,
                        repo_workdir=docker_workdir,
                    )
                    future_to_mid[fut] = mid
                
                # Collect results
                for fut in as_completed(future_to_mid):
                    mid = future_to_mid[fut]
                    try:
                        patch_content = fut.result()
                        if patch_content:
                            results[mid] = patch_content
                    except Exception as e:
                        tqdm.write(f"[ERROR] Module {mid}: {e}")
                    finally:
                        pbar.update(1)
    
    elapsed = round(time.time() - start_time, 1)
    print(f"Generated patches: {len(results)}/{total_tasks} in {elapsed}s")
    return results


class PatchGenerator:
    """High-level interface for patch generation."""
    
    def __init__(
        self,
        image_name: str,
        docker_workdir: str = "/testbed",
        worker_concurrency: int = 10,
        container_concurrency: int = 5,
    ):
        """Initialize patch generator.
        
        Args:
            image_name: Docker image for containers
            docker_workdir: Working directory in containers
            worker_concurrency: Parallel worker count
            container_concurrency: Container pool size
        """
        self.image_name = image_name
        self.docker_workdir = docker_workdir
        self.worker_concurrency = worker_concurrency
        self.container_concurrency = container_concurrency
    
    def generate_patches(
        self,
        modules_data: List[Dict[str, Any]],
        repo_path: str,
    ) -> Dict[str, str]:
        """Generate patches for modules.
        
        Args:
            modules_data: Module data with entities
            repo_path: Repository path
            
        Returns:
            Dictionary of module ID to patch content
        """
        return gen_module_patches_parallel(
            modules_data=modules_data,
            repo_path=repo_path,
            image_name=self.image_name,
            docker_workdir=self.docker_workdir,
            worker_concurrency=self.worker_concurrency,
            container_concurrency=self.container_concurrency,
        )
