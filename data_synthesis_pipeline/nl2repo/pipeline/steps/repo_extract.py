"""Repository extraction step - extracts code from Docker images."""

import io
import os
import tarfile
from typing import List, Optional, Tuple

from tqdm import tqdm

from nl2repo.pipeline.context import PipelineContext
from nl2repo.models.task import MetaInfo

try:
    import docker
except ImportError:
    docker = None


class RepoExtractStep:
    """Extracts repository code from Docker images to local filesystem.
    
    This step pulls Docker images and extracts the /testbed directory
    to a local path for analysis.
    """
    
    def __init__(self, src_path: str = "/testbed"):
        """Initialize repo extract step.
        
        Args:
            src_path: Path inside container to extract
        """
        if docker is None:
            raise ImportError("docker package is required for RepoExtractStep")
        
        self.src_path = src_path
        self.client = docker.from_env()
    
    def run(self, context: PipelineContext) -> None:
        """Execute repository extraction for all repos.
        
        Args:
            context: Pipeline context with meta_list populated
        """
        context.log_progress("RepoExtract", f"Extracting {len(context.meta_list)} repos")
        
        for meta in tqdm(context.meta_list, desc="Extracting repos", ncols=70):
            dest_path = context.get_repo_local_path(meta.repo)
            
            try:
                self.extract_single(meta.image_name, dest_path)
                meta.local_repo_path = dest_path
            except Exception as e:
                context.add_error(f"Failed to extract {meta.repo}: {e}")
    
    def extract_single(
        self,
        image_name: str,
        dest_path: str,
    ) -> None:
        """Extract repository from a single Docker image.
        
        Args:
            image_name: Docker image name
            dest_path: Local destination path
        """
        # Check if already extracted
        success_marker = os.path.join(dest_path, "__SUCCESS__")
        if os.path.exists(success_marker):
            return
        
        clean_src_path = self.src_path.rstrip("/")
        root_folder_name = os.path.basename(clean_src_path)
        
        container = None
        try:
            # Start temporary container
            container = self.client.containers.run(
                image_name,
                command="tail -f /dev/null",
                detach=True,
            )
            
            # Get archive stream
            stream, stat = container.get_archive(clean_src_path)
            
            # Read into memory
            file_obj = io.BytesIO()
            for chunk in stream:
                file_obj.write(chunk)
            file_obj.seek(0)
            
            # Create destination
            os.makedirs(dest_path, exist_ok=True)
            
            # Extract with path manipulation
            with tarfile.open(fileobj=file_obj) as tar:
                members = []
                for member in tar.getmembers():
                    # Skip root directory itself
                    if member.name == root_folder_name or member.name == f"{root_folder_name}/":
                        continue
                    
                    # Strip root prefix
                    if member.name.startswith(f"{root_folder_name}/"):
                        member.name = member.name[len(root_folder_name) + 1:]
                        members.append(member)
                
                tar.extractall(path=dest_path, members=members)
            
            # Mark success
            with open(success_marker, "w") as f:
                f.write("")
                
        except docker.errors.ImageNotFound:
            raise RuntimeError(f"Image not found: {image_name}")
        except docker.errors.NotFound:
            raise RuntimeError(f"Path not found in container: {self.src_path}")
        finally:
            if container:
                try:
                    container.stop()
                    container.remove()
                except Exception:
                    pass
    
    def pull_images(
        self,
        image_names: List[str],
        parallel: int = 4,
    ) -> List[Tuple[str, bool]]:
        """Pull multiple Docker images.
        
        Args:
            image_names: List of image names to pull
            parallel: Number of parallel pulls (not implemented)
            
        Returns:
            List of (image_name, success) tuples
        """
        results = []
        
        for image_name in tqdm(image_names, desc="Pulling images", ncols=70):
            try:
                self.client.images.pull(image_name)
                results.append((image_name, True))
            except Exception as e:
                print(f"Failed to pull {image_name}: {e}")
                results.append((image_name, False))
        
        return results