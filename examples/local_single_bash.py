"""local example"""
from code_data_agent.agent.agent import Agent
from code_data_agent.llm_server.llm_server_http import LLMServerHTTP
from code_data_agent.sandbox.scripts import SCRIPT_BASH_FUNC
from code_data_agent.sandbox.sandbox_local import SandboxLocal
from code_data_agent.tools.tool_bash_executor import ToolBashExecutor
from code_data_agent.llm_server.llm_server_http import LLMServerHTTP


def main():
    """main."""
    # 1. 构造sandbox
    scripts = [SCRIPT_BASH_FUNC]
    sandbox = SandboxLocal(python_bin="python3", scripts=scripts)

    # 2. 构造工具
    tools = [ToolBashExecutor()]

    # 3. 构造LLM服务器
    llm_server = LLMServerHTTP(base_url="http://example:8080/v1", model="qwen2.5-32b")

    # 4. 构造agent
    agent = Agent(
        system_prompt="你是一个善于调用工具完成任务的终端助手。",
        tools=tools,
        llm_server=llm_server,
        sandbox=sandbox,
    )

    agent_run_result = agent.run(
        "请执行三个步骤：\
        1. 尝试删除/tmp/test.txt文件，2. 在 /tmp 下重新创建 test.txt 文件，3. 往/tmp/test.txt中写入'hello world'"
    )
    print(agent_run_result.to_dict())


if __name__ == "__main__":
    main()
