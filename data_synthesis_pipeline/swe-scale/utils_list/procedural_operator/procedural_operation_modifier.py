import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from typing import *
from tree_sitter import Language, Parser, Query, QueryCursor, Node
from utils_list.procedural_operator.procedural_base_modifier import BaseTreeSitterModifier, Edit
from utils_list.data_structure.base_data_structure import CodeEntity


class OperationChangeModifier(BaseTreeSitterModifier):
    explanation: str = "The operations in an expressions are likely incorrect."
    name: str = "func_pm_op_change"
    query_key: str = "CHANGE_OPERATOR"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_binary_operations', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        if 'target' not in captures or not captures['target']:
            return None
            
        target_node = captures['target'][0]
        operator_node = captures['operator'][0] if 'operator' in captures and captures['operator'] else None
        
        if not operator_node:
            return None
            
        operator_text = operator_node.text.decode('utf8')
        
        # Define operator groups similar to original logic      
        new_operator = None
        
        for group in self.language_syntax_dict['CHANGE_OPERATORS_GROUPS'].values():
            if operator_text in group:
                new_operator_list = [op for op in group if op != operator_text]
                if len(new_operator_list) == 0:
                    continue
                new_operator = self.rand.choice(new_operator_list)
                break
        
        if new_operator:
            return [(operator_node.start_byte, operator_node.end_byte, new_operator.encode('utf8'))]
        
        return None


class OperationFlipOperatorModifier(BaseTreeSitterModifier):
    explanation: str = "The operators in an expression are likely incorrect."
    name: str = "func_pm_flip_operators"
    query_key: str = "FLIP_OPERATOR"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results['is_function'],
            entity.filter_results.get('has_binary_operations', False) or \
            entity.filter_results.get('has_boolean_operations', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        if 'target' not in captures or not captures['target']:
            return None
            
        target_node = captures['target'][0]
        operator_node = captures['operator'][0] if 'operator' in captures and captures['operator'] else None
        
        if not operator_node:
            return None
            
        operator_text = operator_node.text.decode('utf8')
        
        # Define flipped operators mapping
        FLIPPED_OPERATORS = self.language_syntax_dict['FLIPPED_OPERATORS']

        new_operator = FLIPPED_OPERATORS.get(operator_text, None)
        
        if new_operator:
            return [(operator_node.start_byte, operator_node.end_byte, new_operator.encode('utf8'))]
        
        return None


class OperationSwapOperandsModifier(BaseTreeSitterModifier):
    explanation: str = "The operands in an expression are likely in the wrong order."
    name: str = "func_pm_op_swap"
    query_key: str = "SWAP_OPERANDS"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results['is_function'],
            entity.filter_results.get('has_binary_operations', False) or \
            entity.filter_results.get('has_boolean_operations', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        required_captures = ['target', 'left', 'right']
        if not all(key in captures for key in required_captures):
            return None

        target_node = captures['target'][0]
        left_node = captures['left'][0]
        right_node = captures['right'][0]

        left_text = left_node.text
        right_text = right_node.text
        
        edits = [
            (left_node.start_byte, left_node.end_byte, right_text),
            (right_node.start_byte, right_node.end_byte, left_text),
        ]
        
        return edits


class OperationBreakChainsModifier(BaseTreeSitterModifier):
    explanation: str = "There are expressions or mathematical operations that are likely incomplete."
    name: str = "func_pm_op_break_chains"
    query_key: str = "BREAK_CHAINS"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_binary_operations', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        """
        计算打断链条所需的编辑指令。
        这个方法是概率性的，并且其逻辑是语言无关的。
        """
        # 从 captures 中安全地获取我们需要的节点
        sub_expression_node = captures.get("sub_expression", [None])[0]
        operand_node = captures.get("operand", [None])[0]
        
        # 如果 Query 没有完整捕获到所需的部分，则不进行任何操作
        if not sub_expression_node or not operand_node:
            return None
        
        # 核心逻辑：
        # 用最深层的操作数 (@operand) 的文本，
        # 去替换掉它所属的那个子表达式 (@sub_expression) 的文本。
        #
        # 示例 (Python): 在 a + b + c 中
        # @sub_expression 是 `a + b`
        # @operand 是 `a`
        # 我们用 `a` 的文本，去替换掉 `a + b` 的文本。
        # 最终 a + b + c 就会安全地变成 a + c。

        replacement_text = operand_node.text
        
        return [(
            sub_expression_node.start_byte,
            sub_expression_node.end_byte,
            replacement_text
        )]


class OperationChangeConstantsModifier(BaseTreeSitterModifier):
    explanation: str = "The constants in an expression might be incorrect."
    name: str = "func_pm_op_change_const"
    query_key: str = "CHANGE_CONSTANTS"
    
    def condition(self, entity: CodeEntity) -> bool:
        flag_list = [
            entity.filter_results.get('is_function', False),
            entity.filter_results.get('has_binary_operations', False),
            entity.complexity >= self.min_complexity_threshold,
        ]
        return all(flag_list)

    def _compute_edits(self, captures: Dict[str, List[Node]], source_bytes: bytes) -> List[Edit] | None:
        if 'integer' not in captures or not captures['integer']:
            return None
        
        edits = []
        
        for integer_node in captures['integer']:
            if not self.flip():
                continue
            # 过滤掉不在有效上下文中的整数
            if not self._is_in_valid_context(integer_node):
                continue
            try:
                integer_text = integer_node.text.decode('utf8')
                
                # 处理不同进制的整数
                if integer_text.startswith('0x') or integer_text.startswith('0X'):
                    int_value = int(integer_text, 16)
                    new_value = int_value + self.rand.choice([-1, 1])
                    new_text = hex(new_value)
                elif integer_text.startswith('0o') or integer_text.startswith('0O'):
                    int_value = int(integer_text, 8)
                    new_value = int_value + self.rand.choice([-1, 1])
                    new_text = oct(new_value)
                elif integer_text.startswith('0b') or integer_text.startswith('0B'):
                    int_value = int(integer_text, 2)
                    new_value = int_value + self.rand.choice([-1, 1])
                    new_text = bin(new_value)
                else:
                    int_value = int(integer_text)
                    new_value = int_value + self.rand.choice([-1, 1])
                    new_text = str(new_value)
                
                # 保持原始格式
                if integer_text.startswith('0x'):
                    new_text = new_text.lower().replace('0x', '0x')
                elif integer_text.startswith('0X'):
                    new_text = new_text.upper().replace('0X', '0X')
                elif integer_text.startswith('0o'):
                    new_text = new_text.lower().replace('0o', '0o')
                elif integer_text.startswith('0O'):
                    new_text = new_text.upper().replace('0O', '0O')
                elif integer_text.startswith('0b'):
                    new_text = new_text.lower().replace('0b', '0b')
                elif integer_text.startswith('0B'):
                    new_text = new_text.upper().replace('0B', '0B')
                
                edits.append((integer_node.start_byte, integer_node.end_byte, new_text.encode('utf8')))
                
            except (ValueError, AttributeError):
                continue
        
        return edits if edits else None
    
    def _is_in_valid_context(self, integer_node: Node) -> bool:
        """检查整数是否在有效的上下文中"""
        # 检查是否在函数定义内
        if not self._is_in_function_context(integer_node):
            return False
        # 检查父节点类型
        parent = integer_node.parent
        if not parent:
            return False
        valid_parent_types = self.language_syntax_dict['CHANGE_CONSTANTS_VALID_PARENTS']
        return parent.type in valid_parent_types
    
    def _is_in_function_context(self, node: Node) -> bool:
        """检查节点是否在函数定义内部"""
        current = node
        while current and current.parent:
            if current.type in self.language_syntax_dict['FUNCTION_CONTEXT_TYPES']:
                return True
            current = current.parent
        return False