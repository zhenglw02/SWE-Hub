"""Pydantic settings for nl2repo pipeline configuration."""

import os
from functools import lru_cache
from typing import Dict, List, Optional, Set

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nl2repo.config.defaults import (
    DEFAULT_CONTAINER_ENV,
    DEFAULT_CPU_REQUEST,
    DEFAULT_MEMORY_REQUEST,
    DEFAULT_TIMEOUT,
    DEFAULT_WORKDIR,
)


class Settings(BaseSettings):
    """Central configuration for nl2repo pipeline.
    
    All settings can be overridden via environment variables with NL2REPO_ prefix.
    Example: NL2REPO_K8S_NAMESPACE=my-namespace
    """
    
    model_config = SettingsConfigDict(
        env_prefix="NL2REPO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Kubernetes configuration
    k8s_namespace: str = Field(
        default="data-synthesis",
        description="Kubernetes namespace for pod execution"
    )
    kubeconfig_path: Optional[str] = Field(
        default=None,
        description="Path to kubeconfig file"
    )
    
    # Container resources
    cpu_request: str = Field(
        default=DEFAULT_CPU_REQUEST,
        description="CPU request for containers"
    )
    memory_request: str = Field(
        default=DEFAULT_MEMORY_REQUEST,
        description="Memory request for containers"
    )
    workdir: str = Field(
        default=DEFAULT_WORKDIR,
        description="Default working directory in containers"
    )
    
    # Timeouts
    coverage_timeout: int = Field(
        default=DEFAULT_TIMEOUT,
        description="Timeout for coverage collection in seconds"
    )
    patch_timeout: int = Field(
        default=60,
        description="Timeout for patch generation in seconds"
    )
    
    # Parallelism
    worker_concurrency: int = Field(
        default=10,
        description="Number of parallel workers for task execution"
    )
    container_concurrency: int = Field(
        default=5,
        description="Number of parallel containers in pool"
    )
    
    # Proxy settings (optional)
    http_proxy: Optional[str] = Field(
        default=None,
        description="HTTP proxy URL"
    )
    https_proxy: Optional[str] = Field(
        default=None,
        description="HTTPS proxy URL"
    )
    
    # Language config paths (external dependency - kept as absolute paths for now)
    language_config_paths: List[str] = Field(
        default=[],
        description="Paths to language configuration YAML files"
    )
    
    # Coverage config path
    coverage_rcfile: str = Field(
        default="",
        description="Path to coverage.ini configuration file"
    )
    
    def get_container_environment(self) -> Dict[str, str]:
        """Build container environment variables dict."""
        env = DEFAULT_CONTAINER_ENV.copy()
        
        if self.http_proxy:
            env["HTTP_PROXY"] = self.http_proxy
            env["http_proxy"] = self.http_proxy
        if self.https_proxy:
            env["HTTPS_PROXY"] = self.https_proxy
            env["https_proxy"] = self.https_proxy
            env["ALL_PROXY"] = self.https_proxy
        
        return env


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
