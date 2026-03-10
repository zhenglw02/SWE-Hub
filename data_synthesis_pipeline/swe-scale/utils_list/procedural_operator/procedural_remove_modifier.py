import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from typing import *
from tree_sitter import Language, Parser, Query, QueryCursor, Node
from utils_list.procedural_operator.procedural_base_modifier import BaseTreeSitterModifier, Edit
from utils_list.data_structure.base_data_structure import CodeEntity


class RemoveLoopModifier(BaseTreeSitterModifier):
    explanation: str = "A loop has been removed."
    name: str = "func_pm_remove_loop"
    query_key: str = "FIND_LOOPS"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_loops', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        # 这是一个概率性 Modifier，因为它需要从所有匹配的循环中随机选择一个来删除
        loop_node = captures.get("loop", [None])[0]
        if not loop_node:
            return None
            
        # 生成一个编辑指令，用空字节替换整个循环节点的文本
        return [(loop_node.start_byte, loop_node.end_byte, b'')]


class RemoveConditionalModifier(BaseTreeSitterModifier):
    explanation: str = "A conditional statement has been removed."
    name: str = "func_pm_remove_cond"
    query_key: str = "FIND_CONDITIONALS"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_conditionals', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        conditional_node = captures.get("conditional", [None])[0]
        if not conditional_node:
            return None
            
        return [(conditional_node.start_byte, conditional_node.end_byte, b'')]


class RemoveAssignModifier(BaseTreeSitterModifier):
    explanation: str = "An assignment statement has been removed."
    name: str = "func_pm_remove_assign"
    query_key: str = "FIND_ASSIGNMENTS"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_assignments', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        assignment_node = captures.get("assignment", [None])[0]
        if not assignment_node:
            return None
            
        return [(assignment_node.start_byte, assignment_node.end_byte, b'')]


class RemoveWrapperModifier(BaseTreeSitterModifier):
    explanation: str = "A wrapper block (with, try) has been removed."
    name: str = "func_pm_remove_wrapper"
    query_key: str = "FIND_WRAPPERS"

    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_wrappers', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None: 
        wrapper_node = captures.get("wrapper", [None])[0]
        if not wrapper_node:
            return None

        return [(wrapper_node.start_byte, wrapper_node.end_byte, b'')]


class UnwrapWrapperModifier(BaseTreeSitterModifier):
    explanation: str = (
        "A wrapper (with, try) has been unwrapped, "
        "preserving its main body but removing the wrapper itself."
    )
    name: str = "func_pm_unwrap_wrapper_ts"
    query_key: str = "FIND_WRAPPERS_WITH_BODY"
    
    def condition(self, entity: CodeEntity) -> bool:
        # condition 逻辑保持不变
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_wrappers', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        wrapper_node = captures.get("wrapper", [None])[0]
        body_block_node = captures.get("body", [None])[0]
        
        if not wrapper_node or not body_block_node:
            return None

        # --- 核心解包逻辑 (简化版) ---
        
        # 1. 检查 body block 是否为空
        if not body_block_node.named_children:
            # 如果 body 为空 (e.g., try: pass)，则解包后也应该为空
            replacement_text = b""
        else:
            # 2. 提取出 body block 内部的所有纯语句内容。
            #    我们通过获取第一个语句的起始位置和最后一个语句的结束位置，
            #    来精确地“裁剪”出所有语句，而排除掉 body block 的外壳
            #    (例如 Python 中的 ':' 和换行，或 C++/Java 中的 '{' 和 '}')。
            
            first_statement = body_block_node.named_children[0]
            last_statement = body_block_node.named_children[-1]
            
            replacement_text = source_bytes[first_statement.start_byte : last_statement.end_byte]

        # 3. 生成一个编辑指令：
        #    用我们刚刚提取出的、纯净的 body 内容，替换掉整个 wrapper 节点。
        return [(
            wrapper_node.start_byte,
            wrapper_node.end_byte,
            replacement_text
        )]