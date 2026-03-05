"""example for k8s sandbox"""

import json
from pathlib import Path

from code_data_agent.agent.agent import Agent
from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
from code_data_agent.model.llm_server import Message
from code_data_agent.sandbox.scripts import SCRIPT_BASH_FUNC
from code_data_agent.sandbox.sandbox_k8s import SandboxK8s
from code_data_agent.tools.tool_bash_executor import ToolBashExecutor
from code_data_agent.llm_server.llm_server_http import LLMServerHTTP


def main():
    """main."""
    # 1. 构造sandbox
    scripts = [SCRIPT_BASH_FUNC]
    base_dir = Path(__file__).resolve().parents[0]
    sandbox = SandboxK8s(
        pod_name="zlw-test-1",
        namespace="data-synthesis",
        kubeconfig_path=str(base_dir / "data" / "data-synthesis.kubeconfig"),
        image="example_docker_image:latest",
        workdir="/workspace",
        conda_dir="/opt/miniconda3",
        conda_env="testbed",
        python_bin="python3",
        scripts=scripts,
        # max_life_time=1
    )

    # 2. 构造工具
    tools = [ToolBashExecutor()]

    # 3. 构造LLM服务器
    llm_server = LLMServerHTTP(
        base_url="http://example:8080/v1",
        model="qwen2.5-32b",
        model_args={"temperature": 0.0},
    )

    # 4. 构造agent
    agent = Agent(
        system_prompt="你是一个善于调用工具完成任务的终端助手。",
        tools=tools,
        llm_server=llm_server,
        sandbox=sandbox,
    )

    agent_run_result = agent.run(
        "请在 /tmp 下创建 test.txt 文件。然后通过conda info判断当前的conda环境名称是什么。注意：请分两步执行"
    )
    print(json.dumps(agent_run_result.to_dict(), indent=2, ensure_ascii=False))

    # 后处理，此时sandbox还在，可以手动执行script或命令

    # 清理sandbox
    sandbox.close()


if __name__ == "__main__":
    main()
