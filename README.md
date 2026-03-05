# code-data-agent-sdk

A toolkit for synthesizing high-quality code training data using LLM agents. It provides three independent pipelines, each producing a different type of training data from real open-source repositories.

## Overview

| Pipeline | What it produces |
|----------|-----------------|
| `env_agent` | Reproducible `install_script` + `test_script` for each repo, plus a runnable Docker image |
| `bug_agent` | Subtle bug patches (PASS→FAIL regressions) paired with realistic GitHub-style issue reports |
| `nl2repo` | Function-level and project-level natural language documentation paired with code patches |

All three pipelines share the `code_data_agent` core SDK, which provides the ReAct agent loop, LLM HTTP client, sandbox abstractions, and tool implementations.

## Prerequisites

- Python >= 3.10
- [Poetry](https://python-poetry.org/) for dependency management
- Docker (required by `env_agent` image builder and `nl2repo`)
- Kubernetes access via the `kodo` platform (required by `env_agent` and `bug_agent` K8s sandboxes)
- An OpenAI-compatible LLM API endpoint

## Installation

```bash
poetry install
```

## Environment Variables

| Variable | Required by | Description |
|----------|-------------|-------------|
| `LLM_BASE_URL` | all pipelines | LLM API base URL (OpenAI-compatible, e.g. `https://api.example.com/v2`) |
| `QIANFAN_BEARER_TOKEN` | all pipelines | Bearer token for LLM API authentication |
| `PIPELINE_PROXY` | `env_agent`, `bug_agent` | HTTP/HTTPS proxy injected into sandbox pods (e.g. `http://user:pass@host:port`) |

All variables can also be passed as CLI arguments. Environment variables serve as defaults.

---

## Pipeline 1: env_agent

Automates environment setup for open-source repositories. For each repo it:
1. Launches a K8s sandbox pod from the repo's Docker image
2. Runs an LLM agent to install dependencies and discover the test runner
3. Extracts `<install_script>` and `<test_script>` from the agent's output
4. Optionally builds a new Docker image with dependencies pre-installed

### Input JSONL format

```json
{
  "repo":          "owner__repo__commit",
  "repo_name":     "owner__repo__commit",
  "image_name":    "your-registry/swesmith.x86_64:latest",
  "reformat_path": "/path/to/source/on/host"
}
```

### Run

```bash
export LLM_BASE_URL="https://api.example.com/v2"
export QIANFAN_BEARER_TOKEN="your-token"
export PIPELINE_PROXY="http://user:pass@proxy-host:port"   # optional

python -m env_agent.main \
  --input repos.jsonl \
  --output-root ./output \
  --namespace data-synthesis \
  --skip-existing
```

### Key options

| Option | Default | Description |
|--------|---------|-------------|
| `--input` | required | Input JSONL path |
| `--output-root` | `./output` | Root directory for per-repo JSON output |
| `--skip-existing` | false | Skip repos that already have output files |
| `--continue-on-error` | false | Keep going after per-repo failures |
| `--max-iterations` | 100 | Max agent iterations (stage 1 / single-stage) |
| `--stage2-max-iterations` | 60 | Max agent iterations for JS/TS stage 2 |
| `--namespace` | `data-synthesis` | K8s namespace |
| `--pod-prefix` | `code-data-env-agent` | Pod name prefix |
| `--cpu-request` | `2` | Pod CPU request |
| `--memory-request` | `5Gi` | Pod memory request |
| `--run-timeout` | 1800 | Sandbox command timeout (seconds) |
| `--log-level` | `INFO` | Logging level: `DEBUG/INFO/WARNING/ERROR` |

### Output

One JSON file per repo under `<output-root>/step_1_env_setup/<repo>.json`:

```json
{
  "status":         "success | max_iteration | tool_stop | error",
  "install_script": "#!/bin/bash ...",
  "test_script":    "#!/bin/bash ...",
  "summary":        "...",
  "messages":       [],
  "error":          null
}
```

---

## Pipeline 2: bug_agent

Injects subtle bugs into Python repositories, verifies PASS→FAIL test regressions, then generates realistic GitHub-style issue reports describing the bug from a user's perspective.

The pipeline has two steps that can be run separately or together:
- **preprocess**: validates the repo environment and collects ground-truth test results
- **bug_issue**: runs the bug injection agent, generates the git patch, and produces the issue report

### Input JSONL format

```json
{
  "repo":              "owner__repo__commit",
  "image_name":        "your-registry/image:installed",
  "test_case_result":  [{"name": "test_foo", "status": "PASSED"}, ...]
}
```

### Run

```bash
export LLM_BASE_URL="https://api.example.com/v2"
export QIANFAN_BEARER_TOKEN="your-token"
export PIPELINE_PROXY="http://user:pass@proxy-host:port"   # optional

# Run all steps
python -m bug_agent.main \
  --steps all \
  --input input.jsonl \
  --output enriched.jsonl \
  --output-root ./output

# Run steps separately
python -m bug_agent.main --steps preprocess --input input.jsonl --output enriched.jsonl
python -m bug_agent.main --steps bug_issue  --input enriched.jsonl --output-root ./output
```

### Key options

| Option | Default | Description |
|--------|---------|-------------|
| `--input` | required | Input JSONL path |
| `--output` | | Output JSONL path (required for preprocess step) |
| `--output-root` | `./output` | Root directory for bug_issue JSON output |
| `--report-root` | `./reports` | Root directory for preprocess reports |
| `--steps` | `all` | Steps to run: `preprocess`, `bug_issue`, or `all` |
| `--skip-existing` | false | Skip repos with existing preprocess output |
| `--continue-on-error` | false | Keep going after per-repo failures |
| `--namespace` | `data-synthesis` | K8s namespace |
| `--pod-prefix` | `code-data-bug-agent` | Pod name prefix |
| `--log-level` | `INFO` | Logging level |

### Output

One JSON file per repo under `<output-root>/step_1_bug_issue/<repo>.json`, containing the bug patch, issue report, and PASS→FAIL test statistics.

---

## Pipeline 3: nl2repo

Extracts code entities from Docker images, builds test-coverage dependency graphs, generates function-body-stripped patches, and uses LLM agents to produce structured natural language documentation.

The pipeline runs through up to 7 steps:

| Step | Name | Description |
|------|------|-------------|
| 0 | `extract` | Pull repo source from Docker image to local disk |
| 1 | `coverage` | Run pytest inside container, collect coverage JSON |
| 2 | `meta` | Parse XML reports, aggregate per-repo metadata |
| 3 | `relationship` | Parse code with tree-sitter, build test→function dependency graph (Louvain clustering), generate `strip_body` patches |
| 4 | `doc_part2` | LLM agent generates function-level documentation (parallel) |
| 5 | `doc_part1` | LLM agent generates project-level documentation (parallel) |
| 6 | `doc` | Assemble final structured document |

### Input JSONL format

```json
{
  "repo":             "owner/repo",
  "image_name":       "your-registry/image:installed",
  "base_commit":      "abc123def456",
  "test_case_result": [{"name": "test_foo", "status": "PASSED"}, ...]
}
```

### Run

```bash
export LLM_BASE_URL="https://api.example.com/v2"
export QIANFAN_BEARER_TOKEN="your-token"

# Run full pipeline
python -m nl2repo.main \
  --input meta.jsonl \
  --output ./output

# Run specific steps
python -m nl2repo.main \
  --input meta.jsonl \
  --output ./output \
  --steps extract,meta,relationship

# Parallel mode (for coverage collection)
python -m nl2repo.main \
  --input meta.jsonl \
  --output ./output \
  --parallel \
  --workers 64
```

### Key options

| Option | Default | Description |
|--------|---------|-------------|
| `--input` | required | Input JSONL path |
| `--output` | required | Output directory |
| `--steps` | `all` | Comma-separated steps or `all` |
| `--parallel` | false | Enable parallel coverage collection |
| `--workers` | 3 | Number of parallel workers |
| `--num-runs` | 10 | Coverage collection runs per repo |

> **Note:** `--llm-base-url` and `--llm-auth-token` are only required when running `doc_part1` or `doc_part2` steps.

---

## Core SDK: code_data_agent

The SDK can also be used independently to build custom agents.

```python
from code_data_agent.agent.agent import Agent
from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
from code_data_agent.sandbox.sandbox_local import SandboxLocal
from code_data_agent.sandbox.scripts import SCRIPT_BASH_FUNC
from code_data_agent.tools.tool_bash_executor import ToolBashExecutor

sandbox = SandboxLocal(python_bin="python3", scripts=[SCRIPT_BASH_FUNC])

llm_server = LLMServerHTTP(
    base_url="https://api.example.com/v2",
    model="your-model-name",
)

agent = Agent(
    system_prompt="You are a helpful coding assistant.",
    tools=[ToolBashExecutor()],
    llm_server=llm_server,
    sandbox=sandbox,
)

result = agent.run("List all Python files under /tmp")
print(result.to_dict())

sandbox.close()
```

For Kubernetes-based sandboxes, use `SandboxK8s`. Note that `SandboxK8s` requires the `kodo` platform, which is not publicly distributed. See `code_data_agent/sandbox/sandbox_k8s.py` for details.

---

## Project Structure

```
code-data-agent-sdk/
├── code_data_agent/                  # Core SDK
│   ├── agent/                        # ReAct agent loop
│   ├── llm_server/                   # OpenAI-compatible HTTP client
│   ├── model/                        # Data models
│   ├── sandbox/                      # Sandbox abstractions (local / K8s)
│   └── tools/                        # Built-in tool implementations
└── data_synthesis_pipeline/
    ├── env_agent/                    # Pipeline 1: environment setup
    │   ├── pipeline/
    │   │   └── steps/
    │   │       ├── env_setup.py      # Main execution step
    │   │       └── image_builder.py  # Docker image build step
    │   └── prompts/                  # LLM system prompts
    ├── bug_agent/                    # Pipeline 2: bug injection + issue generation
    │   ├── pipeline/
    │   │   └── steps/
    │   │       ├── preprocess.py
    │   │       └── bug_issue.py
    │   └── prompts/
    └── nl2repo/                      # Pipeline 3: NL documentation
        ├── agents/                   # DocPart1Agent, DocPart2Agent
        ├── analyzers/                # Dependency graph, Louvain clustering
        ├── generators/               # Patch generation, Docker container pool
        ├── parsers/                  # tree-sitter entity extraction
        └── pipeline/
            └── steps/
```
