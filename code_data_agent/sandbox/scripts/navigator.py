"""navigator script"""

import argparse
import json
import os
import sys
import random
import time
class RepoNavigator:
    """Repo Navigator"""
    def __init__(self, analyze_report_path: str):
        """
        Args:
            analyze_report_path: 完整的知识图谱 JSON 文件路径
        """
        self.analyze_report_path = analyze_report_path
        self.data = self._load_data()
        self.definitions = self.data.get("definitions", {})
        self.hotspots = self.data.get("hotspots", [])
        
        self.children_map = {} 
        self._build_children_map()
    
    def _load_data(self):
        """直接从完整路径加载数据"""
        if not self.analyze_report_path:
            sys.stderr.write("Error: analyze_report_path is empty\n")
            return {}
            
        try:
            with open(self.analyze_report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            sys.stderr.write(f"Warning: Knowledge graph not found at {self.analyze_report_path}\n")
            return {}
        except Exception as e:
            sys.stderr.write(f"Error loading knowledge graph: {e}\n")
            return {"error": str(e)}

    def _build_children_map(self):
        """
        预处理：将扁平的 definitions 转为层级关系
        A.method -> children_map[A] = [method]
        """
        for qname in self.definitions:
            if '.' in qname:
                parent = ".".join(qname.split('.')[:-1])
                if parent in self.definitions: # 确保父节点存在
                    if parent not in self.children_map:
                        self.children_map[parent] = []
                    self.children_map[parent].append(qname)


    def get_hotspots(self, start_index=0, end_index=10):
        """Get hotspots with pagination and random sampling."""
        if not self.data:
            return "Error: Knowledge graph not loaded."

        # 1. 全量随机洗牌
        pool = self.hotspots[:]
        random.seed(time.time())
        random.shuffle(pool)

        # 2. 切片 (保持对文件级别的分页，防止一次吐出整个仓库几千个文件)
        try:
            s, e = int(start_index), int(end_index)
        except:
            s, e = 0, 10
        
        if s >= len(pool): s = 0
        if e > len(pool): e = len(pool)
        
        current_batch = pool[s:e]
        
        result = [f"--- Hotspots (Random Selection from {len(pool)} items) ---"]
        
        for i, item in enumerate(current_batch):
            rank = s + i + 1
            qname = item['qname']
            
            s_line = item.get('start_line', '?')
            e_line = item.get('end_line', '?')
            file_info = f"{item['file']}:L{s_line}-L{e_line}"
            result.append(f"[{rank}] {item.get('type','?')} {qname} ({file_info})")
            
            # [核心修改] 类内部方法：不做截断，全部展示
            if item.get('type') == 'class':
                children = self.children_map.get(qname, [])
                if not children:
                    # 兜底查找
                    prefix = qname + "."
                    children = [k for k in self.definitions if k.startswith(prefix) and '.' not in k[len(prefix):]]
                
                # 依然保留随机洗牌，这样 Agent 每次看到的顺序不同，防止它总是选第一个
                random.shuffle(children)
                
                if children:
                    result.append(f"      Available Methods ({len(children)}):")
                    # [修改] 遍历所有 children，不再使用 [:5]
                    for child_qname in children:
                        short_name = child_qname.split('.')[-1]
                        c_info = self.definitions.get(child_qname, {})
                        c_s = c_info.get('start_line', '?')
                        c_e = c_info.get('end_line', '?')
                        result.append(f"      - {short_name} (L{c_s}-L{c_e})")
            
            result.append("")
            
        return "\n".join(result)

    def inspect_symbol(self, qname):
        """Inspect a symbol (class or method) and gather info."""
        if not self.data:
            return "Error: repo_knowledge.json not found."
        
        if qname not in self.definitions:
            search_suffix = "." + qname if not qname.startswith(".") else qname
            suffix_matches = [k for k in self.definitions if k.endswith(search_suffix)]
            if len(suffix_matches) == 1:
                qname = suffix_matches[0]
            else:
                candidates = [k for k in self.definitions.keys() if qname in k]
                if candidates:
                    candidates.sort(key=len)
                    return f"Symbol '{qname}' not found. Did you mean:\n" + "\n".join(candidates[:5])
                return f"Error: Symbol '{qname}' not found."
        
        info = self.definitions[qname]
        calls = info.get('calls', [])
        all_callers = info.get('called_by', [])
        
        test_callers = [c for c in all_callers if self._is_looks_like_test(c)]
        source_callers = [c for c in all_callers if not self._is_looks_like_test(c)]
        
        member_methods = []
        if info.get('type') == 'class':
            children = self.children_map.get(qname, [])
            if not children:
                prefix = qname + "."
                children = [k for k in self.definitions if k.startswith(prefix) and '.' not in k[len(prefix):]]
            member_methods = children

        loc_str = f"{info['file']}:L{info.get('start_line','?')}-L{info.get('end_line','?')}"

        output = [
            f"=== Symbol Information ===",
            f"Name: {qname}",
            f"Type: {info.get('type', 'unknown')}",
            f"Location: {loc_str}",
            f""
        ]

        # [修改] Member Methods：全部展示，按行号排序方便阅读
        if member_methods:
            output.append(f"--- Member Methods ({len(member_methods)}) ---")
            output.append("(You can select one of these to inject bugs)")
            member_methods.sort(key=lambda x: self.definitions[x].get('start_line', 0))
            for m in member_methods:
                m_short = m.split('.')[-1]
                m_info = self.definitions[m]
                output.append(f"  - {m_short} (L{m_info.get('start_line','?')})")
            output.append("")

        # [修改] 放宽依赖关系的显示上限到 100
        output.append(f"--- 1. Logic Dependencies (Calls) ---")
        if calls:
            output.extend([f"  -> {c}" for c in calls[:100]]) 
            if len(calls) > 100: output.append(f"  ... and {len(calls)-100} more.")
        else:
            output.append("  (No detected outgoing calls)")
        output.append("")

        output.append(f"--- 2. Usage Context (Called By Source) ---")
        if source_callers:
            output.extend([f"  <- {c}" for c in source_callers[:100]])
            if len(source_callers) > 100: output.append(f"  ... and {len(source_callers)-100} more.")
        else:
            output.append("  (No detected source callers)")
        output.append("")

        output.append(f"--- 3. Verification Points (Called By Tests) ---")
        if test_callers:
            output.extend([f"  [TEST] {t}" for t in test_callers[:100]])
            if len(test_callers) > 100: output.append(f"  ... and {len(test_callers)-100} more.")
        else:
            # [核心修改] 智能提示逻辑
            # 判断当前符号是不是一个类的方法 (名字包含点，且父节点存在且为 Class)
            is_method_in_class = False
            parent_name = None
            
            if '.' in qname:
                parent_name = ".".join(qname.split('.')[:-1])
                # 简单查一下父节点是不是类
                if parent_name in self.definitions and self.definitions[parent_name].get('type') == 'class':
                    is_method_in_class = True

            if is_method_in_class:
                # 针对方法的特殊提示：不做定论，引导去查类
                output.append("  (No direct method coverage detected via static analysis.)")
                output.append("  [HINT] This is a Class Method. Integration tests often verify the Class directly.")
                output.append(f"  [ACTION] Please `inspect_symbol('{parent_name}')` to see class-level tests.")
            else:
                # 普通函数或类，确实没找到
                output.append("  (No direct test coverage detected!)")

        return "\n".join(output)

    def _is_looks_like_test(self, qname):
        """
        判断一个 QName 是否属于测试代码。
        策略：优先查 definitions 看文件路径；查不到则回退到名字猜测。
        """
        # 1. 查表 (最准)
        if qname in self.definitions:
            file_path = self.definitions[qname]['file']
            # 这里可以用你在 Config 里定义的 FILE_PATTERNS，或者简单的关键词
            return any(p in file_path for p in ["/tests", "/test", "test_"])
            
        # 2. 兜底 (查不到定义时，比如外部库调用，虽然这种情况很少出现在 called_by 里)
        return 'test' in qname.lower().split('.')[-1] # 只检查最后一段，避免包名包含test

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["get_hotspots", "inspect_symbol"])
    parser.add_argument("--analyze_report_path", required=True, help="Full path to knowledge graph JSON")
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--end_index", type=int, default=10)
    parser.add_argument("--qname", type=str, default="") 
    
    args = parser.parse_args()
    
    navigator = RepoNavigator(args.analyze_report_path)
    
    if args.action == "get_hotspots":
        print(navigator.get_hotspots(args.start_index, args.end_index))
    elif args.action == "inspect_symbol":
        if not args.qname:
            print("Error: --qname is required for inspect_symbol")
        else:
            print(navigator.inspect_symbol(args.qname))