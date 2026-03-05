"""Simple data containers used by sandbox implementations."""

ARG_COMMAND = "command"

class SandboxRunResult(object):
    """Represents the result of executing a command inside the sandbox."""

    def __init__(self, exit_code: int, output: str):
        """Capture the process exit code and aggregated stdout/stderr text."""
        self.exit_code = exit_code
        # 字符串格式，AI主要参考的结果
        self.output = output

    def to_dict(self):
        """Serialize the result to a JSON-friendly dictionary."""
        return {
            "exit_code": self.exit_code,
            "output": self.output,
        }


class SandboxScript(object):
    """Stores metadata for a script that can run inside the sandbox."""

    def __init__(self, name: str, path: str):
        """Record the script name and absolute path."""
        self.name = name
        self.path = path

    def to_dict(self):
        """Serialize the script metadata."""
        return {
            "name": self.name,
            "path": self.path,
        }
