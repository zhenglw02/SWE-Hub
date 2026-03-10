# SWE-Scale

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> 自动化代码Bug数据合成Pipeline，为代码理解与修复AI模型生成高质量的训练数据

---

## Overview

**SWE-Scale** is a comprehensive pipeline for automatically synthesizing realistic code bug data from real-world codebases. Inspired by [SWE-Smith](https://swesmith.com/), this project generates buggy code patches, validates them with actual test suites, and creates realistic GitHub issue descriptions for training and evaluating AI code models.

### Key Features

- **Multi-strategy Bug Generation**
  - Procedural generation using AST-based transformations
  - LLM-based bug introduction (modify and rewrite modes)
  - Combined bug generation for complex scenarios

- **Multi-language Support**
  - Python, JavaScript, TypeScript, C/C++, Go, Java, PHP, Ruby, Rust
  - Extensible architecture for adding new languages

- **Automated Validation**
  - Docker-based isolated test execution
  - Pass-to-Fail (P2F) detection for real bug verification
  - Parallel execution for scalability

- **Realistic Issue Generation**
  - LLM-powered GitHub issue creation
  - Based on actual test failures and code context
  - Mimics real-world issue reporting style

### Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Stage 0: Configuration                        │
│  - Repository setup (clone, docker image build)                 │
│  - Configuration management                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Stage 1: Bug Generation                      │
│  ├─ Step 1: Procedural bug generation (cost-free)               │
│  ├─ Step 2: LLM bug generation (modify mode)                    │
│  ├─ Step 2: LLM bug generation (rewrite mode)                   │
│  └─ Step 3: Combine multiple bugs                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Stage 2: Validation                           │
│  - Run test suite with empty patch (ground truth)               │
│  - Run test suite with single bug patches                       │
│  - Run test suite with combined bug patches                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Stage 3: Report Parsing                      │
│  - Parse test output (pass/fail classification)                │
│  - Identify Pass-to-Fail (P2F) instances                        │
│  - Export validated bug patches                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Stage 4: Issue Generation                     │
│  ├─ Step 1: Generate realistic GitHub issues                    │
│  └─ Step 2: Export final dataset with issues                    │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.8+
- Docker
- (Optional) Kubernetes cluster for distributed execution

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd swe-scale

# Install dependencies
pip install -r requirements.txt

# Optional: Install Kodo SDK for K8s-based container management
# git clone https://github.com/baidubce/kodo
# cd kodo && pip install -e .
```

## Quick Start

### 1. Configure a Repository

Create a configuration file in `config_list/`:

```python
# config_list/your_repo__commit_hash.py
from pathlib import Path

class Config:
    REPO_NAME = "your_repo__commit_hash"
    COMMIT = "full_commit_hash"
    IMAGE_NAME = "your_docker_image:latest"
    LANGUAGE = "PYTHON"
    BASE_PATH = Path("./config_list/repo_list")

    # Log directories
    LOG_DIR = LOG_PATH / Path("logs_{}".format(REPO_NAME))
    LOG_DIR_BUG_GEN = LOG_PATH / Path("logs_{}/bug_gen".format(REPO_NAME))
    LOG_DIR_ISSUE_GEN = LOG_PATH / Path("logs_{}/issue_gen".format(REPO_NAME))

    # Bug generation parameters
    PROCEDURAL_MAX_BUGS = 2000
    REWRITE_MAX_BUGS = 2000
    MODIFY_MAX_BUGS = 2000

    # LLM configuration
    BUG_GEN_MODEL_NAME = "openai/your-model"
    API_KEY = "your_api_key"
    API_BASE = "https://your-api-endpoint"

    # Pytest configuration
    TEST_SCRIPT = 'pytest -n 10 --disable-warnings --color=no'
```

### 2. Run the Pipeline

```bash
# Set up repository and docker image
# 1. Download repository to config_list/repo_list/
# 2. Build/pull docker image

# Stage 1: Generate bugs
python stage_1_swe_smith/step_1_procedural_gen_bug.py --config_name your_repo__commit_hash
python stage_1_swe_smith/step_2_llm_gen_bug.py --config_name your_repo__commit_hash --bug_type modify
python stage_1_swe_smith/step_2_llm_gen_bug.py --config_name your_repo__commit_hash --bug_type rewrite
python stage_1_swe_smith/step_3_combine_bug.py --config_name your_repo__commit_hash

# Stage 2: Validate bugs
python stage_2_validation/step_1_evalution_ground_truth.py --config_name your_repo__commit_hash
python stage_2_validation/step_1_evalution_cross_repo_script.py --config_name your_repo__commit_hash --bug_mode single
python stage_2_validation/step_1_evalution_cross_repo_script.py --config_name your_repo__commit_hash --bug_mode combine

# Stage 3: Parse reports
python stage_3_report_parser/step_0_parse_gound_truth_cross_repo_python_xml.py --config_name your_repo__commit_hash
python stage_3_report_parser/step_1_parse_report_cross_repo_python_xml.py --config_name your_repo__commit_hash --bug_mode single
python stage_3_report_parser/step_1_parse_report_cross_repo_python_xml.py --config_name your_repo__commit_hash --bug_mode combine
python stage_3_report_parser/step_2_export_instance.py --config_name your_repo__commit_hash --bug_mode single
python stage_3_report_parser/step_2_export_instance.py --config_name your_repo__commit_hash --bug_mode combine

# Stage 4: Generate issues
python stage_4_gen_issue/step_1_generate_issue.py --config_name your_repo__commit_hash
python stage_4_gen_issue/step_2_export_final_data.py --config_name your_repo__commit_hash
```

Or use the provided `run.sh` script as a template for automation.

## Bug Generation Strategies

### Procedural Generation

Procedural generation uses AST-based transformations to introduce bugs without LLM cost:

- **Operation Modifiers**: Change operators, flip signs, swap operands
- **Control Flow Modifiers**: Invert if/else conditions, shuffle lines
- **Class Modifiers**: Remove base classes, shuffle methods, remove functions
- **Remove Modifiers**: Remove loops, conditionals, assignments, wrappers

### LLM-based Generation

LLM-based generation uses large language models to create more sophisticated bugs:

- **Modify Mode**: Subtly modify existing code to introduce bugs
- **Rewrite Mode**: Completely rewrite code sections while introducing bugs

## Configuration

### Bug Generation Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `PROCEDURAL_MAX_BUGS` | Maximum procedural bugs | 2000 |
| `REWRITE_MAX_BUGS` | Maximum LLM rewrite bugs | 2000 |
| `MODIFY_MAX_BUGS` | Maximum LLM modify bugs | 2000 |
| `SEED` | Random seed for reproducibility | 42 |

### LLM Configuration

| Parameter | Description |
|-----------|-------------|
| `BUG_GEN_MODEL_NAME` | Model for bug generation |
| `ISSUE_GEN_MODEL_NAME` | Model for issue generation |
| `API_KEY` | API authentication key |
| `API_BASE` | API endpoint URL |

### Execution Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `CONTAINER_CONCURRENCY` | Concurrent containers | 50 |
| `WORKER_CONCURRENCY` | Parallel workers | 50 |
| `TIMEOUT` | Test timeout (seconds) | 600 |

## Output Format

### Bug Patch Format

Each bug instance generates:
- `metadata__{instance_id}.json`: Metadata about the bug
- `bug__{instance_id}.diff`: Git diff format patch

```json
{
  "instance_id": "procedural__OperationChangeModifier__abc123",
  "hash_code": "abc123",
  "rewrite": "buggy_code_here",
  "explanation": "Changed operator from + to *",
  "cost": 0.0,
  "strategy": "OperationChangeModifier",
  "output": "buggy_code_here"
}
```

### Final Dataset Format

```jsonl
{
  "instance_id": "django__asgiref__796b9f14.bug__llm__lm_modify__6a820bd6__0001",
  "repo": "django__asgiref__796b9f14",
  "image_name": "iregistry.baidu-int.com/acg-airec/r2e_gym/my_swe_smith/swesmith.x86_64.django__asgiref.796b9f14:latest",
  "base_commit": "796b9f14fd92d3131c7c39fab308ddd986d271eb",
  "patch": "diff --git a/asgiref/compatibility.py b/asgiref/compatibility.py\nindex 3a2a63e..bcfd38e 100644\n--- a/asgiref/compatibility.py\n+++ b/asgiref/compatibility.py\n@@ -7,24 +7,17 @@ def is_double_callable(application):\n...",
  "problem_statement": "is_double_callable returns False for uninstantiated classes after a recent change...",
  "FAIL_TO_PASS": ["tests.test_compatibility::test_is_double_callable"],
  "PASS_TO_PASS": ["tests.test_sync.ASGITest::test_wrapped_case_is_collected", "..."],
  "eval_sh": "#!/bin/sh\nset -u\ncd /testbed\nif [ -f \"/opt/miniconda3/bin/activate\" ]; then ...",
  "created_at": "2026-03-04T16:33:40.994464",
  "version": null,
  "meta": {
    "test_output": "",
    "raw_path": "/path/to/bug__llm__lm_modify__6a820bd6__0001.diff",
    "log_parser": "parse_log_pytest_xdist"
  }
}
```

**Field Descriptions:**

| Field | Description |
|-------|-------------|
| `instance_id` | Unique identifier for the bug instance |
| `repo` | Repository name with commit hash |
| `image_name` | Docker image used for testing |
| `base_commit` | Full commit hash of the repository version |
| `patch` | Git diff format patch that introduces the bug |
| `problem_statement` | Realistic GitHub issue description |
| `FAIL_TO_PASS` | Tests that should fail with the bug (P2F) |
| `PASS_TO_PASS` | Tests that should pass regardless of the bug |
| `eval_sh` | Shell script for running evaluation |
| `created_at` | Timestamp when the instance was created |
| `version` | Version field (nullable) |
| `meta` | Metadata including test output, raw path, and log parser |

## Project Structure

```
swe-scale/
├── config_list/              # Repository configurations
│   ├── repo_list/           # Downloaded repositories
│   └── *.py                 # Config files per repository
├── stage_0_register_config/ # Configuration registration
├── stage_1_swe_smith/       # Bug generation
│   ├── step_1_procedural_gen_bug.py
│   ├── step_2_llm_gen_bug.py
│   ├── step_3_combine_bug.py
│   └── prompt_yaml_list/   # LLM prompts
├── stage_2_validation/      # Bug validation
├── stage_3_report_parser/   # Result parsing
├── stage_4_gen_issue/       # Issue generation
│   ├── step_1_generate_issue.py
│   ├── step_2_export_final_data.py
│   └── issue_gen/          # Issue generation prompts
└── utils_list/             # Shared utilities
    ├── procedural_operator/ # AST-based modifiers
    ├── language_config/    # Language-specific configs
    ├── container_utils/    # Docker/K8s utilities
    └── ...
```

## Supported Languages

| Language | Status | Parser |
|----------|--------|--------|
| Python | ✅ Full Support | pytest |
| JavaScript | ✅ Full Support | jest/mocha |
| TypeScript | ✅ Full Support | jest/mocha |
| C/C++ | ✅ Full Support | googletest |
| Go | ✅ Full Support | go test |
| Java | ✅ Full Support | JUnit |
| PHP | ✅ Full Support | PHPUnit |
| Ruby | ✅ Full Support | RSpec |
| Rust | ✅ Full Support | cargo test |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by [SWE-Smith](https://swesmith.com/)
- Uses [tree-sitter](https://github.com/tree-sitter/tree-sitter) for AST parsing
- Built on [SWE-bench](https://github.com/princeton-nlp/SWE-bench) evaluation framework

## Citation

If you use this project in your research, please cite:

```bibtex
@misc{zeng2026swehubunifiedproductionscalable,
      title={SWE-Hub: A Unified Production System for Scalable, Executable Software Engineering Tasks}, 
      author={Yucheng Zeng and Shupeng Li and Daxiang Dong and Ruijie Xu and Zimo Chen and Liwei Zheng and Yuxuan Li and Zhe Zhou and Haotian Zhao and Lun Tian and Heng Xiao and Tianshu Zhu and Longkun Hao and Jianmin Wu},
      year={2026},
      eprint={2603.00575},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2603.00575}, 
}
```

## Contact

For questions and feedback, please open an issue or contact [yucheng-zeng@outlook.com].
