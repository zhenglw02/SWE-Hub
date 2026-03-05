"""Static call graph analysis tool for Part 2 documentation."""

import os
import ast
import networkx as nx
from typing import Any, Dict, Optional
from collections import defaultdict

from code_data_agent.model.tool import (
    ToolInvokeResult,
    TOOL_INVOKER_STATUS_SUCCESS,
    TOOL_INVOKER_STATUS_FAIL,
)
from code_data_agent.sandbox.sandbox_base import SandboxBase
from code_data_agent.tools.tool_base import ToolBase


class SimplePythonCallGraph:
    """Build a static call graph from Python source files using AST analysis."""
    
    def __init__(self, repo_root: str):
        """__init__."""
        self.repo_root = os.path.abspath(repo_root)
        self.G = nx.DiGraph()
        self.definitions = defaultdict(dict)
        self.files = self._scan_files()
        self._build_definitions()
        self._resolve_calls()

    def _scan_files(self):
        """_scan_files."""
        py_files = []
        for root, _, files in os.walk(self.repo_root):
            for file in files:
                if file.endswith(".py"):
                    py_files.append(os.path.join(root, file))
        return py_files

    def _get_rel_path(self, abs_path):
        """_get_rel_path."""
        return os.path.relpath(abs_path, self.repo_root)

    def _build_definitions(self):
        """_build_definitions."""
        for file_path in self.files:
            rel_path = self._get_rel_path(file_path)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    tree = ast.parse(f.read(), filename=file_path)
                
                visitor = _DefinitionVisitor(rel_path)
                visitor.visit(tree)
                self.definitions[rel_path] = visitor.defs
                
                for qname in visitor.defs.values():
                    node_id = f"{file_path}::{qname}"
                    self.G.add_node(node_id, type="function", filepath=file_path)
                    
            except Exception:
                pass

    def _resolve_calls(self):
        """_resolve_calls."""
        for file_path in self.files:
            rel_path = self._get_rel_path(file_path)
            if rel_path not in self.definitions:
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    tree = ast.parse(f.read())
                
                local_defs = self.definitions[rel_path]
                visitor = _CallVisitor(rel_path, local_defs, self.definitions)
                visitor.visit(tree)
                
                for caller, callee_list in visitor.calls.items():
                    caller_id = f"{file_path}::{caller}"
                    
                    for callee_file_rel, callee_name in callee_list:
                        callee_abs = os.path.join(self.repo_root, callee_file_rel)
                        callee_id = f"{callee_abs}::{callee_name}"
                        
                        if callee_id in self.G:
                            self.G.add_edge(caller_id, callee_id)
                            
            except Exception:
                pass

    def get_successors(self, node_id: str) -> list:
        """Get functions called BY this node."""
        if node_id in self.G:
            return list(self.G.successors(node_id))
        return []

    def get_predecessors(self, node_id: str) -> list:
        """Get functions that call this node."""
        if node_id in self.G:
            return list(self.G.predecessors(node_id))
        return []


class _DefinitionVisitor(ast.NodeVisitor):
    def __init__(self, rel_path):
        """__init__."""
        self.rel_path = rel_path
        self.defs = {}
        self.current_class = None

    def visit_FunctionDef(self, node):
        """visit_FunctionDef."""
        if self.current_class:
            qname = f"{self.current_class}.{node.name}"
        else:
            qname = node.name
        self.defs[qname] = qname
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        """visit_AsyncFunctionDef."""
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        """visit_ClassDef."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class


class _CallVisitor(ast.NodeVisitor):
    def __init__(self, rel_path, local_defs, all_definitions):
        """__init__."""
        self.rel_path = rel_path
        self.local_defs = local_defs
        self.all_definitions = all_definitions
        self.imports = {}
        self.current_scope = None
        self.calls = defaultdict(list)
        self.current_class = None

    def visit_Import(self, node):
        """visit_Import."""
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            self.imports[asname] = name

    def visit_ImportFrom(self, node):
        """visit_ImportFrom."""
        module = node.module or ""
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            if module:
                self.imports[asname] = f"{module}.{name}"
            else:
                self.imports[asname] = name

    def visit_ClassDef(self, node):
        """visit_ClassDef."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        """visit_FunctionDef."""
        if self.current_class:
            func_name = f"{self.current_class}.{node.name}"
        else:
            func_name = node.name
            
        old_scope = self.current_scope
        self.current_scope = func_name
        self.generic_visit(node)
        self.current_scope = old_scope

    def visit_Call(self, node):
        """visit_Call."""
        if not self.current_scope:
            return
        
        target_name = self._get_func_name(node.func)
        if not target_name:
            return

        if target_name.startswith("self.") and self.current_class:
            method_name = target_name.split(".")[1]
            qname = f"{self.current_class}.{method_name}"
            if qname in self.local_defs:
                self.calls[self.current_scope].append((self.rel_path, qname))
                return

        if target_name in self.local_defs:
            self.calls[self.current_scope].append((self.rel_path, self.local_defs[target_name]))
            return

        parts = target_name.split(".")
        head = parts[0]
        
        if head in self.imports:
            real_path = self.imports[head]
            potential_rel_path = real_path.replace(".", "/") + ".py"
            
            if len(parts) > 1:
                func_part = parts[1]
                if potential_rel_path in self.all_definitions:
                    if func_part in self.all_definitions[potential_rel_path]:
                        self.calls[self.current_scope].append((potential_rel_path, func_part))
                        return
            
            if "." in real_path:
                mod_part, func_part = real_path.rsplit(".", 1)
                mod_file = mod_part.replace(".", "/") + ".py"
                if mod_file in self.all_definitions:
                    if func_part in self.all_definitions[mod_file]:
                        self.calls[self.current_scope].append((mod_file, func_part))

    def _get_func_name(self, node):
        """_get_func_name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_func_name(node.value)
            if base:
                return f"{base}.{node.attr}"
        return None


class ToolStaticCallGraph(ToolBase):
    """Get static call graph relations for a given node."""
    
    def __init__(self, grapher: SimplePythonCallGraph, local_workdir: str, kodo_workdir: str):
        """Initialize with pre-built call graph.
        
        Args:
            grapher: Pre-built SimplePythonCallGraph instance
            local_workdir: Local repository path
            kodo_workdir: Container repository path (e.g., /testbed)
        """
        self.grapher = grapher
        self.local_workdir = local_workdir
        self.kodo_workdir = kodo_workdir
    
    def get_name(self) -> str:
        """get_name."""
        return "GET_STATIC_CALL_GRAPH_RELATIONS"
    
    def get_description(self) -> str:
        """get_description."""
        return (
            "Analyze the codebase using STATIC ANALYSIS (AST-based) to retrieve "
            "the call graph relationships for a given node.\n\n"
            "This tool reveals the code structure without execution:\n"
            "1. **Successors**: Functions called BY the target node.\n"
            "2. **Predecessors**: Functions that call the target node.\n\n"
            "Use this for: Code Navigation, Dependency Analysis, and understanding "
            "Refactoring Impacts."
        )
    
    def get_parameters(self) -> Dict[str, Any]:
        """get_parameters."""
        return {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": (
                        "The unique identifier of the target node in the exact format: "
                        "'absolute_file_path::function_name' "
                        "(e.g., '/testbed/src/utils.py::MyClass.run')."
                    )
                }
            },
            "required": ["node_name"]
        }
    
    def invoke(self, sandbox: SandboxBase, **kwargs) -> ToolInvokeResult:
        """invoke."""
        node_name = kwargs.get("node_name", "")
        
        if not node_name:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_FAIL,
                content="Missing required parameter 'node_name'",
                need_call_llm=True,
            )
        
        # Convert kodo path to local path for lookup
        local_node_name = node_name.replace(self.kodo_workdir, self.local_workdir)
        
        if local_node_name not in self.grapher.G:
            return ToolInvokeResult(
                status=TOOL_INVOKER_STATUS_SUCCESS,
                content=(
                    f"The node '{node_name}' was not found in the static graph. "
                    "Please check the file path and function name. "
                    "Ensure the format is 'absolute_path::qname' "
                    "(e.g. /testbed/path/to/file.py::ClassName.method)"
                ),
                need_call_llm=True,
            )
        
        # Get relations
        successors = self.grapher.get_successors(local_node_name)
        successors = [item.replace(self.local_workdir, self.kodo_workdir) for item in successors]
        
        predecessors = self.grapher.get_predecessors(local_node_name)
        predecessors = [item.replace(self.local_workdir, self.kodo_workdir) for item in predecessors]
        
        result = {
            "status": "success",
            "query_node": node_name,
            "relations": {
                "successors": {
                    "description": "Functions called BY the target node (Out-bound).",
                    "count": len(successors),
                    "nodes": sorted(successors)
                },
                "predecessors": {
                    "description": "Functions that call the target node (In-bound).",
                    "count": len(predecessors),
                    "nodes": sorted(predecessors)
                }
            }
        }
        
        import json
        return ToolInvokeResult(
            status=TOOL_INVOKER_STATUS_SUCCESS,
            content=json.dumps(result, ensure_ascii=False, indent=2),
            need_call_llm=True,
        )