import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from typing import *
from tree_sitter import Language, Parser, Query, QueryCursor, Node
from utils_list.procedural_operator.procedural_base_modifier import BaseTreeSitterModifier, Edit
from utils_list.data_structure.base_data_structure import CodeEntity


class ControlIfElseInvertModifier(BaseTreeSitterModifier):
    explanation: str = "The if-else conditions may be out of order, or the bodies are inverted."
    name: str = "func_pm_ctrl_invert_if"
    query_key: str = "INVERT_IF_ELSE"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_if_else', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        if_body_node = captures.get("if_body", [None])[0]
        else_body_node = captures.get("else_body", [None])[0]
        
        if not if_body_node or not else_body_node:
            return None
            
        # 直接从 Node 获取正确的文本
        if_body_text = if_body_node.text
        else_body_text = else_body_node.text
        
        # 返回两个独立的、精确的指令
        edits = [
            (if_body_node.start_byte, if_body_node.end_byte, else_body_text),
            (else_body_node.start_byte, else_body_node.end_byte, if_body_text),
        ]
        return edits


class ControlIfElifInvertModifier(BaseTreeSitterModifier):
    explanation: str = "The if-elif conditions may be out of order, or the bodies are inverted."
    name: str = "func_pm_ctrl_invert_if_elif"
    query_key: str = "INVERT_IF_ELIF"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_if_else', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        if_body_node = captures.get("if_body", [None])[0]
        # 关键变化：捕获 @elif_body 而不是 @else_body
        elif_body_node = captures.get("elif_body", [None])[0] 
        
        if not if_body_node or not elif_body_node:
            return None
            
        if_body_text = if_body_node.text
        elif_body_text = elif_body_node.text
        
        edits = [
            (if_body_node.start_byte, if_body_node.end_byte, elif_body_text),
            (elif_body_node.start_byte, elif_body_node.end_byte, if_body_text),
        ]
        
        return edits


class ControlShuffleLinesModifier(BaseTreeSitterModifier):
    explanation: str = "The lines inside a function may be out of order."
    name: str = "func_pm_ctrl_shuffle"
    query_key: str = "SHUFFLE_FUNCTION_BODY"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.complexity >= self.min_complexity_threshold,
            entity.complexity <= self.max_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:    
        function_body_node = captures.get("function_body", [None])[0]
        if not function_body_node:
            return None
            
        # 1. 提取出所有可被重排的顶级语句节点
        #    我们只处理 body 的直接子节点，以避免破坏内部块的结构
        statements = [child for child in function_body_node.children if self._is_statement(child)]
        
        if len(statements) < 2:
            return None
        # 最后一句不打乱，因为很有可能是 return 语句
        statements = statements[:-1]
        # 2. 创建一个原始语句的副本，并将其随机打乱
        shuffled_statements = statements.copy()
        # 使用 self.rand 以确保结果可复现
        self.rand.shuffle(shuffled_statements)
        
        # 3. 生成“多重独立编辑”指令列表
        #    这里的逻辑是：对于原始位置 i 上的语句，我们用打乱后
        #    位置 i 上的语句的文本来替换它。
        edits: List[Edit] = []
        for original_node, shuffled_node in zip(statements, shuffled_statements):
            # 获取打乱后节点的原始文本（包含其精确的缩进和格式）
            replacement_text = shuffled_node.text
            
            # 创建一个编辑指令：用新文本替换旧节点的位置
            edit = (
                original_node.start_byte,
                original_node.end_byte,
                replacement_text
            )
            edits.append(edit)
            
        return edits
    
    def _is_statement(self, node: Node) -> bool:
        return node.is_named and node.type not in self.language_syntax_dict['SHUFFLE_LINES_BLACKLIST']