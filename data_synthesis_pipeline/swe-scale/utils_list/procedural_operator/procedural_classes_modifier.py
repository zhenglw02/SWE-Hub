import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from typing import *
from tree_sitter import Language, Parser, Query, QueryCursor, Node
from utils_list.procedural_operator.procedural_base_modifier import BaseTreeSitterModifier, Edit
from utils_list.data_structure.base_data_structure import CodeEntity


class ClassRemoveBasesModifier(BaseTreeSitterModifier):
    explanation: str = "A base class has been removed from the class definition."
    name: str = "func_pm_class_rm_base"
    query_key: str = "REMOVE_CLASS_BASES"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_class', False),
            entity.filter_results.get('has_class_parents', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        
        inheritance_clause_node = captures.get("inheritance_clause", [None])[0]
        if not inheritance_clause_node:
            return None

        # 核心逻辑：生成一个编辑指令，用空字节替换整个继承子句的文本。
        # 这就完成了“一次性移除所有基类”的操作。
        return [(
            inheritance_clause_node.start_byte, 
            inheritance_clause_node.end_byte, 
            b''  # 替换为空字节串，即删除
        )]


class ClassShuffleMethodsModifier(BaseTreeSitterModifier):
    explanation: str = "The methods and attributes in a class have been shuffled."
    name: str = "func_pm_class_shuffle_funcs"
    query_key: str = "SHUFFLE_CLASS_BODY"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_class', False),
            entity.filter_results.get('has_function_definitions', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        class_body_node = captures.get("class_body", [None])[0]
        if not class_body_node:
            return None
            
        # 提取类体中所有顶级的、可被重排的语句
        statements = [child for child in class_body_node.children if child.is_named]
        
        if len(statements) < 2:
            return None
            
        shuffled_statements = statements.copy()
        self.rand.shuffle(shuffled_statements)
        
        # 如果随机结果和原来一样，则不进行任何修改
        if all(s1.id == s2.id for s1, s2 in zip(statements, shuffled_statements)):
            return None

        # 生成“排列置换”的编辑列表
        edits: List[Edit] = []
        for original_node, shuffled_node in zip(statements, shuffled_statements):
            edit = (
                original_node.start_byte,
                original_node.end_byte,
                shuffled_node.text  # 使用 .text 来保留完美的原始格式
            )
            edits.append(edit)
            
        return edits


class ClassRemoveFuncsModifier(BaseTreeSitterModifier):
    explanation: str = "Method(s) have been removed from the class. (Note: references are not removed)"
    name: str = "func_pm_class_rm_funcs"
    query_key: str = "FIND_CLASS_FUNCTIONS"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_class', False),
            entity.filter_results.get('has_function_definitions', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        function_node = captures.get("function", [None])[0]
        if not function_node:
            return None

        # 生成一个编辑指令，用空字节替换整个方法节点的文本，即删除它
        # 我们需要智能地处理前后的换行符，以避免留下过多的空行
        start_byte = function_node.start_byte
        end_byte = function_node.end_byte
        
        # 检查前面的节点，找到真正的起始删除点（包括前面的空行）
        # 这需要更复杂的逻辑来保证格式，简单起见，我们先直接删除节点
        # 一个更健壮的方法是获取节点的 start_point 和 end_point (行号/列号)
        # 然后删除这些整行。但为了简化，我们先直接删除节点文本。
        
        return [(start_byte, end_byte, b'')]
