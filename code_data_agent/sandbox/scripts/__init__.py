"""
R2E (Ready to Execute) Tools Package

Simple, standalone function-level tools that can be:
1. Used as Python functions
2. Executed as command-line tools
3. Integrated with agent systems
"""

from pathlib import Path

from code_data_agent.model.sandbox import SandboxScript

base_dir = Path(__file__).resolve().parents[0]
bash_script = base_dir / "bash_func.py"
navigator_script = base_dir / "navigator.py"
file_editor_script = base_dir / "file_editor.py"
search_script = base_dir / "search_func.py"
repo_analyzer_script = base_dir / "repo_analyzer.py"

SCRIPT_BASH_FUNC = SandboxScript(name="bash_func", path=str(bash_script))
SCRIPT_NAVIGATOR = SandboxScript(name="navigator", path=str(navigator_script))
SCRIPT_FILE_EDITOR = SandboxScript(name="file_editor", path=str(file_editor_script))
SCRIPT_SEARCH_FUNC = SandboxScript(name="search_func", path=str(search_script))
SCRIPT_REPO_ANALYZER = SandboxScript(name="repo_analyzer", path=str(repo_analyzer_script))
