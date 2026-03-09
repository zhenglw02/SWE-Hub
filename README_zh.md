# code-data-agent-sdk

基于 LLM Agent 的高质量代码训练数据合成工具包。提供三条独立流水线，分别从真实开源仓库中生成不同类型的训练数据。

> **技术报告**：[https://arxiv.org/abs/2603.00575](https://arxiv.org/abs/2603.00575)

## 概览

| 流水线 | 产出数据 |
|--------|----------|
| `env_agent` | 每个仓库可复现的 `install_script` + `test_script`，以及可直接运行的 Docker 镜像 |
| `bug_agent` | 微小 Bug 补丁（PASS→FAIL 测试回归）与模拟真实用户视角的 GitHub Issue 报告配对数据 |
| `nl2repo` | 函数级与项目级自然语言文档，与代码补丁配对 |

三条流水线共用 `code_data_agent` 核心 SDK，SDK 提供 ReAct Agent 循环、LLM HTTP 客户端、沙箱抽象层和工具实现。

## 环境要求

- Python >= 3.10
- [Poetry](https://python-poetry.org/) 依赖管理
- Docker（`env_agent` 镜像构建步骤和 `nl2repo` 需要）
- 通过 `kodo` 平台访问 Kubernetes（`env_agent` 和 `bug_agent` 的 K8s 沙箱需要）
- 兼容 OpenAI 接口的 LLM API 服务

## 安装

```bash
poetry install
```

## 环境变量

| 变量 | 适用流水线 | 说明 |
|------|-----------|------|
| `LLM_BASE_URL` | 所有流水线 | LLM API 地址（兼容 OpenAI 格式，例如 `https://api.example.com/v2`） |
| `QIANFAN_BEARER_TOKEN` | 所有流水线 | LLM API 鉴权 Bearer Token |
| `PIPELINE_PROXY` | `env_agent`、`bug_agent` | 注入沙箱 Pod 的 HTTP/HTTPS 代理（例如 `http://user:pass@host:port`） |

所有变量均可通过 CLI 参数传入，环境变量作为默认值。

---

## 流水线一：env_agent

自动化为开源仓库配置可复现的运行环境。对每个仓库执行以下步骤：
1. 基于仓库 Docker 镜像启动 K8s 沙箱 Pod
2. 运行 LLM Agent 安装依赖、发现测试框架
3. 从 Agent 输出中提取 `<install_script>` 和 `<test_script>`
4. 可选：将已安装依赖的容器提交为新的 Docker 镜像

### 输入 JSONL 格式

```json
{
  "repo":          "owner__repo__commit",
  "repo_name":     "owner__repo__commit",
  "image_name":    "your-registry/swesmith.x86_64:latest",
  "reformat_path": "/path/to/source/on/host"
}
```

### 运行

```bash
export LLM_BASE_URL="https://api.example.com/v2"
export QIANFAN_BEARER_TOKEN="your-token"
export PIPELINE_PROXY="http://user:pass@proxy-host:port"   # 可选

python -m env_agent.main \
  --input repos.jsonl \
  --output-root ./output \
  --namespace data-synthesis \
  --skip-existing
```

### 主要参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | 输入 JSONL 文件路径 |
| `--output-root` | `./output` | 每个仓库 JSON 输出的根目录 |
| `--skip-existing` | false | 跳过已有输出文件的仓库 |
| `--continue-on-error` | false | 单个仓库失败后继续处理剩余仓库 |
| `--max-iterations` | 100 | Agent 最大迭代次数（阶段一 / 单阶段） |
| `--stage2-max-iterations` | 60 | JS/TS 双阶段模式阶段二的最大迭代次数 |
| `--namespace` | `data-synthesis` | K8s 命名空间 |
| `--pod-prefix` | `code-data-env-agent` | Pod 名称前缀 |
| `--cpu-request` | `2` | Pod CPU 请求量 |
| `--memory-request` | `5Gi` | Pod 内存请求量 |
| `--run-timeout` | 1800 | 沙箱命令超时时间（秒） |
| `--log-level` | `INFO` | 日志级别：`DEBUG/INFO/WARNING/ERROR` |

### 输出

每个仓库在 `<output-root>/step_1_env_setup/<repo>.json` 下生成一个 JSON 文件：

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

## 流水线二：bug_agent

向 Python 仓库注入微小 Bug，验证测试 PASS→FAIL 回归，然后生成模拟真实用户视角的 GitHub Issue 报告。

流水线包含两个可独立或组合运行的步骤：
- **preprocess**：在 Agent 启动前完成两项离线准备工作：
  1. **测试报告**（K8s sandbox）：在沙箱中执行 pytest，将每条用例的 PASS/FAIL 状态记录到 `{repo}_test_report.json`，作为后续验证 PASS→FAIL 回归的 ground-truth oracle。该功能已集成到 `main.py` 的 preprocess 步骤中，由 `preprocessor/test_report_generator.py` 实现。
  2. **仓库分析**（本地，无需 sandbox）：使用 tree-sitter 解析全部 Python 源文件，提取所有类与函数的全限定名（qname）和行号范围，并通过 import 感知的调用解析构建正向/反向调用图。每个非测试符号按"被多少条 PASSED 测试（传递地）调用"打分并降序排列，最终将包含 **hotspots 排行榜**与**完整 definitions 映射**的结果保存为 `{repo}_analysis.json`。此文件是 bug 注入 Agent 的核心信息来源：`GET_HOTSPOTS` 工具从中读取高影响力的注入候选目标，`INSPECT_SYMBOL` 工具从中获取指定符号的调用方、被调用方及源码位置，辅助 Agent 精确定位并理解要修改的函数。该功能由 `preprocessor/repo_analyzer.py` 实现，已集成到 `main.py` 的 preprocess 步骤中；也可单独运行：

     ```bash
     python data_synthesis_pipeline/bug_agent/preprocessor/repo_analyzer.py \
       --repo-path /path/to/local/repo \
       --repo-name owner__repo__commit \
       --output-dir ./reports/owner__repo__commit \
       [--test-report ./reports/owner__repo__commit/owner__repo__commit_test_report.json] \
       [--config /path/to/lang_config.yaml]
     ```
- **bug_issue**：运行 Bug 注入 Agent，生成 git 补丁，产出 Issue 报告

### 输入 JSONL 格式

```json
{
  "repo":              "owner__repo__commit",
  "image_name":        "your-registry/image:installed",
  "test_case_result":  [{"name": "test_foo", "status": "PASSED"}, ...]
}
```

### 运行

```bash
export LLM_BASE_URL="https://api.example.com/v2"
export QIANFAN_BEARER_TOKEN="your-token"
export PIPELINE_PROXY="http://user:pass@proxy-host:port"   # 可选

# 运行全部步骤
python -m bug_agent.main \
  --steps all \
  --input input.jsonl \
  --output enriched.jsonl \
  --output-root ./output

# 分步运行
python -m bug_agent.main --steps preprocess --input input.jsonl --output enriched.jsonl
python -m bug_agent.main --steps bug_issue  --input enriched.jsonl --output-root ./output
```

### 主要参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | 输入 JSONL 文件路径 |
| `--output` | | 输出 JSONL 路径（preprocess 步骤必填） |
| `--output-root` | `./output` | bug_issue 结果的根目录 |
| `--report-root` | `./reports` | preprocess 报告的根目录 |
| `--steps` | `all` | 要运行的步骤：`preprocess`、`bug_issue` 或 `all` |
| `--skip-existing` | false | 跳过已有 preprocess 输出的仓库 |
| `--continue-on-error` | false | 单个仓库失败后继续处理剩余仓库 |
| `--namespace` | `data-synthesis` | K8s 命名空间 |
| `--pod-prefix` | `code-data-bug-agent` | Pod 名称前缀 |
| `--log-level` | `INFO` | 日志级别 |

### 输出

每个仓库在 `<output-root>/step_1_bug_issue/<repo>.json` 下生成一个 JSON 文件，包含 Bug 补丁、Issue 报告和 PASS→FAIL 测试统计信息。

---

## 流水线三：nl2repo

从 Docker 镜像中提取代码实体，构建测试覆盖率依赖图，生成函数体替换补丁，并通过 LLM Agent 产出结构化自然语言文档。

流水线最多包含 7 个步骤：

| 步骤编号 | 步骤名称 | 说明 |
|---------|---------|------|
| 0 | `extract` | 从 Docker 镜像提取仓库源码到本地磁盘 |
| 1 | `coverage` | 在容器中运行 pytest，采集覆盖率 JSON |
| 2 | `meta` | 解析 XML 报告，聚合每个仓库的元数据 |
| 3 | `relationship` | 用 tree-sitter 解析代码，构建 test→function 依赖图（Louvain 聚类），生成 `strip_body` 补丁 |
| 4 | `doc_part2` | LLM Agent 并行生成函数级文档 |
| 5 | `doc_part1` | LLM Agent 并行生成项目级文档 |
| 6 | `doc` | 组装最终结构化文档 |

### 输入 JSONL 格式

```json
{
  "repo":             "owner/repo",
  "image_name":       "your-registry/image:installed",
  "base_commit":      "abc123def456",
  "test_case_result": [{"name": "test_foo", "status": "PASSED"}, ...]
}
```

### 运行

```bash
export LLM_BASE_URL="https://api.example.com/v2"
export QIANFAN_BEARER_TOKEN="your-token"

# 运行完整流水线
python -m nl2repo.main \
  --input meta.jsonl \
  --output ./output

# 运行指定步骤
python -m nl2repo.main \
  --input meta.jsonl \
  --output ./output \
  --steps extract,meta,relationship

# 并行模式（用于覆盖率采集）
python -m nl2repo.main \
  --input meta.jsonl \
  --output ./output \
  --parallel \
  --workers 64
```

### 主要参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | 输入 JSONL 文件路径 |
| `--output` | 必填 | 输出目录路径 |
| `--steps` | `all` | 逗号分隔的步骤名称，或 `all` |
| `--parallel` | false | 开启并行覆盖率采集 |
| `--workers` | 3 | 并行工作线程数 |
| `--num-runs` | 10 | 每个仓库的覆盖率采集次数 |

> **注意：** `--llm-base-url` 和 `--llm-auth-token` 仅在运行 `doc_part1` 或 `doc_part2` 步骤时必须提供。

---

## 核心 SDK：code_data_agent

SDK 也可以单独使用，用于构建自定义 Agent。

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
    system_prompt="你是一个善于调用工具完成任务的终端助手。",
    tools=[ToolBashExecutor()],
    llm_server=llm_server,
    sandbox=sandbox,
)

result = agent.run("列出 /tmp 下所有 Python 文件")
print(result.to_dict())

sandbox.close()
```

如需使用 Kubernetes 沙箱，请使用 `SandboxK8s`。注意 `SandboxK8s` 依赖 `kodo` 平台，该平台不对外公开分发，详见 `code_data_agent/sandbox/sandbox_k8s.py`。

---

## 项目结构

```
code-data-agent-sdk/
├── code_data_agent/                  # 核心 SDK
│   ├── agent/                        # ReAct Agent 循环
│   ├── llm_server/                   # 兼容 OpenAI 格式的 HTTP 客户端
│   ├── model/                        # 数据模型
│   ├── sandbox/                      # 沙箱抽象层（本地 / K8s）
│   └── tools/                        # 内置工具实现
└── data_synthesis_pipeline/
    ├── env_agent/                    # 流水线一：环境配置
    │   ├── pipeline/
    │   │   └── steps/
    │   │       ├── env_setup.py      # 主执行步骤
    │   │       └── image_builder.py  # Docker 镜像构建步骤
    │   └── prompts/                  # LLM 系统提示词
    ├── bug_agent/                    # 流水线二：Bug 注入 + Issue 生成
    │   ├── pipeline/
    │   │   └── steps/
    │   │       ├── preprocess.py
    │   │       └── bug_issue.py
    │   └── prompts/
    └── nl2repo/                      # 流水线三：NL 文档生成
        ├── agents/                   # DocPart1Agent、DocPart2Agent
        ├── analyzers/                # 依赖图、Louvain 聚类
        ├── generators/               # 补丁生成、Docker 容器池
        ├── parsers/                  # tree-sitter 实体提取
        └── pipeline/
            └── steps/
```
