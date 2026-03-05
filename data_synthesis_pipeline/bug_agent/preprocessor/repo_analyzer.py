"""
仓库分析器：分析仓库结构（类、函数、调用关系）

这是一个离线预处理脚本，在本地运行（不需要sandbox），
使用Tree-sitter解析代码，分析结果保存到CFS供BugIssueAgent使用。
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import yaml
except ImportError:
    yaml = None

try:
    from tree_sitter import Language, Parser, Query, QueryCursor, Node
except ImportError:
    print("Error: tree-sitter libraries are not installed. Run: pip install tree-sitter", file=sys.stderr)
    Language = None
    Parser = None
    Query = None
    QueryCursor = None
    Node = None


# ==================== 配置 ====================

def _default_python_config() -> Dict[str, Any]:
    """默认的Python语言配置"""
    return {
        "name": "Python",
        "indent_size": 4,
        "file_extensions": [".py", ".pyw"],
        "file_patterns": ["/tests", "/test", "/testing", "test_"],
        "namespace_strategy": "implicit",
        "queries": {
            "definitions": (
                "(function_definition name: (identifier) @name) @function\n"
                "(class_definition name: (identifier) @name) @class\n"
            ),
            "calls": (
                "(call\n"
                "  function: [\n"
                "    (identifier) @name\n"
                "    (attribute object: (_) @object attribute: (identifier) @name)\n"
                "  ]\n"
                ") @call\n"
            ),
            "imports": (
                "(import_statement\n"
                "  name: [\n"
                "    (dotted_name) @path\n"
                "    (aliased_import\n"
                "      name: (dotted_name) @path\n"
                "      alias: (identifier) @alias\n"
                "    )\n"
                "  ]\n"
                ") @import\n"
                "\n"
                "(import_from_statement\n"
                "  module_name: [\n"
                "    (dotted_name) @from\n"
                "    (relative_import) @from\n"
                "  ]\n"
                "  name: [\n"
                "    (dotted_name) @name\n"
                "    (aliased_import\n"
                "      name: (dotted_name) @name\n"
                "      alias: (identifier) @alias\n"
                "    )\n"
                "  ]\n"
                ") @import\n"
                "\n"
                "(import_from_statement\n"
                "  module_name: [\n"
                "    (dotted_name) @from\n"
                "    (relative_import) @from\n"
                "  ]\n"
                "  (wildcard_import) @wildcard\n"
                ") @import\n"
            ),
            "package": "",
        },
    }


class AgentNavConfig:
    """语言配置类"""
    
    def __init__(self, config_path: Optional[str] = None):
        """__init__."""
        config_data: Dict[str, Any]
        if config_path and os.path.exists(config_path) and yaml:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
        else:
            config_data = _default_python_config()
        
        self.NAME: str = config_data["name"]
        self.LANGUAGE: Language = self._load_language_object(self.NAME)
        self.EXTENSIONS: Set[str] = set(config_data.get("file_extensions", []))
        self.FILE_PATTERNS: Set[str] = set(config_data.get("file_patterns", []))
        self.NAMESPACE_STRATEGY: str = config_data.get("namespace_strategy", "implicit")
        queries = config_data.get("queries", {})
        self.QUERY_DEFINITIONS: str = queries.get("definitions", "")
        self.QUERY_CALLS: str = queries.get("calls", "")
        self.QUERY_IMPORTS: str = queries.get("imports", "")
        self.QUERY_PACKAGE: str = queries.get("package", "")

    def _load_language_object(self, name: str) -> Language:
        """_load_language_object."""
        name = name.lower()
        if name == "python":
            import tree_sitter_python as tspy
            return Language(tspy.language())
        if name == "java":
            import tree_sitter_java as tsjava
            return Language(tsjava.language())
        if name == "go":
            import tree_sitter_go as tsgo
            return Language(tsgo.language())
        raise ValueError(f"Unsupported language: {name}")


# ==================== 数据结构 ====================

@dataclass
class NodeEntity:
    """代码节点实体"""
    name: str
    qname: str
    type: str
    file_path: str
    start_line: int
    end_line: int
    raw_calls: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class AnalyzeResult:
    """分析结果"""
    success: bool
    output_path: Optional[str] = None
    definitions_count: int = 0
    hotspots_count: int = 0
    error_message: Optional[str] = None


# ==================== 核心分析器 ====================

class RepoMapBuilder:
    """仓库代码结构分析器"""
    
    def __init__(self, repo_path: str, config: AgentNavConfig, report_path: Optional[str]):
        """__init__."""
        self.repo_path = os.path.abspath(repo_path)
        self.config = config
        self.report_path = report_path
        self.passed_tests: Set[str] = set()
        self.parser = Parser(config.LANGUAGE)
        self.q_defs = Query(config.LANGUAGE, config.QUERY_DEFINITIONS) if config.QUERY_DEFINITIONS else None
        self.q_imports = Query(config.LANGUAGE, config.QUERY_IMPORTS) if config.QUERY_IMPORTS else None
        self.q_calls = Query(config.LANGUAGE, config.QUERY_CALLS) if config.QUERY_CALLS else None
        self.q_package = Query(config.LANGUAGE, config.QUERY_PACKAGE) if config.QUERY_PACKAGE else None
        self.definitions: Dict[str, NodeEntity] = {}
        self.import_maps: Dict[str, Dict[str, str]] = {}
        self.call_graph: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_call_graph: Dict[str, Set[str]] = defaultdict(set)
        self.short_name_index: Dict[str, List[str]] = defaultdict(list)

    def load_pytest_report(self) -> None:
        """加载pytest测试报告"""
        if not self.report_path:
            return
        if not os.path.exists(self.report_path):
            print(f"Warning: Report not found at {self.report_path}", file=sys.stderr)
            return
        try:
            with open(self.report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for test_node_id, status in data.items():
                if status == "PASSED":
                    normalized_qname = test_node_id.replace("::", ".")
                    self.passed_tests.add(normalized_qname)
            print(f"Loaded {len(self.passed_tests)} PASSED tests from report.")
        except Exception as e:
            print(f"Warning: Error loading report: {e}", file=sys.stderr)

    def build(self) -> Dict[str, Any]:
        """构建分析报告"""
        self.load_pytest_report()
        # Step 1: Parsing
        for file_path in self._find_files():
            self._parse_file(file_path)
        # Step 2: Resolving
        self._resolve_calls()
        # Step 3: Generating
        return self._generate_report()

    def _find_files(self) -> List[str]:
        """查找所有匹配的源文件"""
        files: List[str] = []
        for root, _, filenames in os.walk(self.repo_path):
            for filename in filenames:
                if any(filename.endswith(ext) for ext in self.config.EXTENSIONS):
                    files.append(os.path.join(root, filename))
        return files

    def _parse_file(self, file_path: str) -> None:
        """解析单个文件"""
        rel_path = os.path.relpath(file_path, self.repo_path)
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except Exception as e:
            print(f"Skipping {rel_path}: {e}", file=sys.stderr)
            return
        tree = self.parser.parse(content)
        scope_prefix = self._get_scope_prefix(tree.root_node, rel_path)
        initial_scope = scope_prefix.split(".")
        self.import_maps[rel_path] = self._extract_imports(tree.root_node)
        self._traverse_and_extract(tree.root_node, initial_scope, rel_path)

    def _traverse_and_extract(self, node: Node, scope_stack: List[str], rel_path: str) -> None:
        """遍历AST并提取定义"""
        node_type = node.type
        is_class = "class" in node_type
        is_func = "function" in node_type or "method" in node_type
        
        if is_class or is_func:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                full_qname = ".".join(scope_stack + [name])
                entity_type = "class" if is_class else "function"
                
                entity = NodeEntity(
                    name=name,
                    qname=full_qname,
                    type=entity_type,
                    file_path=rel_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_calls=[],
                )
                
                if is_func:
                    entity.raw_calls = self._extract_raw_calls(node)
                    
                self.definitions[full_qname] = entity
                self.short_name_index[name].append(full_qname)
                
                if is_class:
                    scope_stack.append(name)
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            self._traverse_and_extract(child, scope_stack, rel_path)
                    scope_stack.pop()
                return
                
        for child in node.children:
            self._traverse_and_extract(child, scope_stack, rel_path)

    def _get_scope_prefix(self, root_node: Node, rel_path: str) -> str:
        """获取作用域前缀"""
        if self.config.NAMESPACE_STRATEGY == "explicit" and self.q_package:
            cursor = QueryCursor(self.q_package)
            captures = cursor.captures(root_node)
            if "name" in captures:
                for node in captures["name"]:
                    return node.text.decode("utf-8")
        base, _ = os.path.splitext(rel_path)
        return base.replace(os.sep, ".")

    def _extract_imports(self, root_node: Node) -> Dict[str, str]:
        """提取import语句"""
        if not self.q_imports:
            return {}
        import_map: Dict[str, str] = {}
        cursor = QueryCursor(self.q_imports)
        matches = cursor.matches(root_node)
        
        for match in matches:
            captures_dict = match[-1] if isinstance(match, tuple) else match
            
            def get_text(key: str) -> Optional[str]:
                """get_text."""
                nodes = captures_dict.get(key, [])
                if isinstance(nodes, list):
                    return nodes[0].text.decode("utf-8") if nodes else None
                return nodes.text.decode("utf-8") if nodes else None

            path = get_text("path")
            from_mod = get_text("from")
            name = get_text("name")
            alias = get_text("alias")
            
            full_name: Optional[str] = None
            local_alias: Optional[str] = None
            
            if path:
                clean_path = path.strip('"')
                full_name = clean_path
                local_alias = alias if alias else clean_path.split(".")[-1]
            elif from_mod and name:
                full_name = f"{from_mod}.{name}"
                local_alias = alias if alias else name
                
            if full_name and local_alias:
                full_name = full_name.replace("/", ".")
                import_map[local_alias] = full_name
        return import_map

    def _extract_raw_calls(self, scope_node: Node) -> List[Dict[str, str]]:
        """提取函数调用"""
        if not self.q_calls:
            return []
        raw_calls: List[Dict[str, str]] = []
        cursor = QueryCursor(self.q_calls)
        matches = cursor.matches(scope_node)
        
        for match in matches:
            captures_dict = match[-1] if isinstance(match, tuple) else match
            info: Dict[str, str] = {}
            for cap_name, val in captures_dict.items():
                node = val[0] if isinstance(val, list) and val else val
                if node:
                    info[cap_name] = node.text.decode("utf-8")
            if "name" in info:
                raw_calls.append(info)
        return raw_calls

    def _fuzzy_find_definition(self, target_qname: str, caller_entity: NodeEntity) -> Optional[str]:
        """模糊查找定义"""
        if target_qname in self.definitions:
            return target_qname
        
        short_name = target_qname.split(".")[-1]
        candidates = self.short_name_index.get(short_name)
        if not candidates:
            return None
            
        if len(candidates) == 1:
            return candidates[0]
            
        required_suffix = "." + target_qname
        strong_matches = [qname for qname in candidates if qname.endswith(required_suffix)]
        if len(strong_matches) == 1:
            return strong_matches[0]
        if strong_matches:
            candidates = strong_matches
            
        scores = []
        caller_imports = self.import_maps.get(caller_entity.file_path, {})
        
        for cand_qname in candidates:
            cand_entity = self.definitions.get(cand_qname)
            if not cand_entity:
                continue
            
            score = 0
            try:
                common_path = os.path.commonpath([caller_entity.file_path, cand_entity.file_path])
                score += len(common_path) * 10
            except ValueError:
                pass
                
            cand_module = ".".join(cand_qname.split(".")[:-1])
            if cand_module in caller_imports.values():
                score += 50
            if not cand_entity.name.startswith("_"):
                score += 5
            scores.append((score, cand_qname))
            
        if scores:
            scores.sort(key=lambda x: (-x[0], len(x[1])))
            return scores[0][1]
        return None

    def _resolve_calls(self) -> None:
        """解析调用关系"""
        for caller_qname, entity in self.definitions.items():
            imports = self.import_maps.get(entity.file_path, {})
            for call in entity.raw_calls:
                target = self._resolve_single_call(call, imports, entity)
                if target:
                    self.call_graph[caller_qname].add(target)
                    self.reverse_call_graph[target].add(caller_qname)

    def _resolve_single_call(
        self, call: Dict[str, str], imports: Dict[str, str], caller_entity: NodeEntity
    ) -> Optional[str]:
        """解析单个调用"""
        name = call.get("name")
        obj = call.get("object")
        if not name:
            return None
        
        # 1. obj.method() where obj is imported
        if obj and obj in imports:
            target_qname = f"{imports[obj]}.{name}"
            found = self._fuzzy_find_definition(target_qname, caller_entity)
            if found:
                return found
            
        # 2. direct_func() where imported
        if not obj and name in imports:
            target_qname = imports[name]
            found = self._fuzzy_find_definition(target_qname, caller_entity)
            if found:
                return found
            
        # 3. Same scope or sibling
        caller_scope = ".".join(caller_entity.qname.split(".")[:-1])
        potential_qname = f"{caller_scope}.{name}"
        found = self._fuzzy_find_definition(potential_qname, caller_entity)
        if found:
            return found
        
        # 4. Parent scope (method calls sibling method in class)
        if "." in caller_scope:
            parent_scope = ".".join(caller_scope.split(".")[:-1])
            potential_parent_func = f"{parent_scope}.{name}"
            found = self._fuzzy_find_definition(potential_parent_func, caller_entity)
            if found:
                return found
            
            if obj:
                potential_sibling_obj = f"{parent_scope}.{obj}.{name}"
                found = self._fuzzy_find_definition(potential_sibling_obj, caller_entity)
                if found:
                    return found
                
        # 5. Wildcard attempts via imports
        if obj:
            for imported_qname in imports.values():
                potential_method_qname = f"{imported_qname}.{name}"
                found = self._fuzzy_find_definition(potential_method_qname, caller_entity)
                if found:
                    return found
        return None

    def _generate_report(self) -> Dict[str, Any]:
        """生成分析报告"""
        node_stats: Dict[str, Dict[str, Any]] = {}
        for qname in self.definitions:
            node_stats[qname] = {
                "tested_by": set(),
                "calls": set(self.call_graph.get(qname, [])),
                "called_by": set(self.reverse_call_graph.get(qname, [])),
            }
            
        # Mapping passed tests to functions
        for qname, callers in self.reverse_call_graph.items():
            if qname not in node_stats:
                continue
            for c in callers:
                if c not in self.definitions:
                    continue
                caller_entity = self.definitions[c]
                is_test_file = any(p in caller_entity.file_path for p in self.config.FILE_PATTERNS)
                is_passed = c in self.passed_tests
                
                if is_test_file and is_passed:
                    node_stats[qname]["tested_by"].add(c)
                    
        # Propagate method coverage to classes
        for qname, entity in self.definitions.items():
            if entity.type == "function":
                parts = qname.split(".")
                if len(parts) > 1:
                    parent_qname = ".".join(parts[:-1])
                    if parent_qname in self.definitions and self.definitions[parent_qname].type == "class":
                        node_stats[parent_qname]["calls"].update(node_stats[qname]["calls"])
                        node_stats[parent_qname]["called_by"].update(node_stats[qname]["called_by"])
                        node_stats[parent_qname]["tested_by"].update(node_stats[qname]["tested_by"])
                        
        hotspots: List[Dict[str, Any]] = []
        final_definitions: Dict[str, Dict[str, Any]] = {}
        top_classes = set()
        all_nodes_with_score: List[Any] = []
        
        for qname, stats in node_stats.items():
            score = len(stats["tested_by"])
            if score >= 0:
                is_test = any(p in self.definitions[qname].file_path for p in self.config.FILE_PATTERNS)
                if not is_test:
                    all_nodes_with_score.append((qname, score))
                    if self.definitions[qname].type == "class":
                        top_classes.add(qname)
                        
        all_nodes_with_score.sort(key=lambda x: x[1], reverse=True)
        
        for qname, score in all_nodes_with_score:
            entity = self.definitions[qname]
            stats = node_stats[qname]
            
            final_definitions[qname] = {
                "type": entity.type,
                "file": entity.file_path,
                "start_line": entity.start_line,
                "end_line": entity.end_line,
                "calls": list(stats["calls"]),
                "called_by": list(stats["called_by"]),
            }
            
            # Hide methods if their Class is already a top hotspot (deduplication)
            is_shadowed = False
            if entity.type == "function":
                parts = qname.split(".")
                if len(parts) > 1 and ".".join(parts[:-1]) in top_classes:
                    is_shadowed = True
                    
            if not is_shadowed:
                entry: Dict[str, Any] = {
                    "qname": qname,
                    "type": entity.type,
                    "file": entity.file_path,
                    "start_line": entity.start_line,
                    "end_line": entity.end_line,
                    "score": score,
                    "tested_by": list(stats["tested_by"]),
                }
                
                if entity.type == "class":
                    child_methods = []
                    for child_qname, child_entity in self.definitions.items():
                        if child_entity.type == "function" and child_qname.startswith(qname + "."):
                            child_score = len(node_stats[child_qname]["tested_by"])
                            child_methods.append({
                                "qname": child_qname,
                                "score": child_score,
                                "start_line": child_entity.start_line,
                                "end_line": child_entity.end_line,
                            })
                    child_methods.sort(key=lambda x: x["score"], reverse=True)
                    entry["top_methods"] = child_methods[:10]
                    
                hotspots.append(entry)
                
        return {"hotspots": hotspots, "definitions": final_definitions}


# ==================== 高级接口 ====================

class RepoAnalyzer:
    """仓库结构分析器（高级接口）"""

    def __init__(self, repo_path: str, output_dir: str):
        """
        初始化分析器
        
        Args:
            repo_path: 本地仓库路径
            output_dir: 输出目录（CFS路径）
        """
        self.repo_path = Path(repo_path).resolve()
        self.output_dir = Path(output_dir)

    def analyze(
        self,
        repo_name: str,
        test_report_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> AnalyzeResult:
        """
        分析仓库结构
        
        Args:
            repo_name: 仓库名称（用于生成输出文件名）
            test_report_path: 可选的pytest测试报告路径（用于映射测试覆盖）
            config_path: 可选的YAML配置文件路径
            
        Returns:
            AnalyzeResult: 分析结果
        """
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{repo_name}_analysis.json"
        
        try:
            # 加载配置
            config = AgentNavConfig(config_path=config_path)
            
            # 构建分析器并执行分析
            builder = RepoMapBuilder(
                str(self.repo_path),
                config,
                report_path=test_report_path,
            )
            report = builder.build()
            
            # 保存结果
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            return AnalyzeResult(
                success=True,
                output_path=str(output_path),
                definitions_count=len(report.get("definitions", {})),
                hotspots_count=len(report.get("hotspots", [])),
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            return AnalyzeResult(
                success=False,
                error_message=str(e),
            )


# ==================== 命令行入口 ====================

def main() -> int:
    """命令行入口"""
    parser = argparse.ArgumentParser(description="分析仓库结构（类、函数、调用关系）")
    parser.add_argument("--repo-path", required=True, help="本地仓库路径")
    parser.add_argument("--repo-name", required=True, help="仓库名称（用于输出文件命名）")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--test-report", default="", help="可选的pytest测试报告路径")
    parser.add_argument("--config", default="", help="可选的YAML配置文件路径")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.repo_path):
        print(f"❌ 错误: 仓库路径不存在 -> {args.repo_path}", file=sys.stderr)
        return 1
    
    analyzer = RepoAnalyzer(
        repo_path=args.repo_path,
        output_dir=args.output_dir,
    )
    
    result = analyzer.analyze(
        repo_name=args.repo_name,
        test_report_path=args.test_report or None,
        config_path=args.config or None,
    )
    
    if result.success:
        summary = {
            "status": "success",
            "output_path": result.output_path,
            "definitions_count": result.definitions_count,
            "hotspots_count": result.hotspots_count,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\n✅ 分析完成，结果保存到: {result.output_path}")
        return 0
    else:
        print(f"❌ 分析失败: {result.error_message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())