import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from typing import *
from tree_sitter import Language, Parser, Query, QueryCursor, Node
from utils_list.data_structure.base_data_structure import CodeEntity
from utils_list.common_utils.common_tools import generate_hash
from utils_list.extract_utils.entity_filters import FilterManager


class LanguageProcessor:
    def __init__(self,
        language: Language, 
        entity_query_string: str,
        complexity_query_string: str,
        filter_queries: dict,
        placeholder_body: str,
        indent_size: int, 
        file_extensions: set, 
        file_patterns: set,
        language_name: str,
    ):
        self.language = language
        self.parser = Parser(language)
        self.entity_query = Query(language, entity_query_string)
        self.complexity_query = Query(language, complexity_query_string)
        self.filter_queries = filter_queries
        self.filter_manager = FilterManager(language, filter_queries)
        self.placeholder_body = placeholder_body
        self.indent_size = indent_size
        self.file_extensions = file_extensions
        self.file_patterns = file_patterns
        self.language_name = language_name

    def get_file_extensions(self) -> Set[str]:
        return self.file_extensions

    def get_test_file_patterns(self) -> Set[str]:
        return self.file_patterns

    def get_entity_from_node(
        self, node: Node, name: str, code_type: str, 
        file_content: str, file_path: str, 
        indent_size: int, file_extension: str
    ) -> CodeEntity:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        source_code = node.text.decode('utf8')
        lines = file_content.splitlines()
        source_line = lines[start_line - 1]
        leading_whitespace = len(source_line) - len(source_line.lstrip())

        effective_indent_size = indent_size
        if "\t" in source_line:
            guessed_size = source_line.expandtabs().find(source_line.lstrip())
            if guessed_size != -1:
                effective_indent_size = guessed_size
            
        indentation_level = (leading_whitespace // effective_indent_size if leading_whitespace > 0 and effective_indent_size > 0 else 0)
        
        code_lines = source_code.splitlines()
        if len(code_lines) > 1:
            dedented_source_code = [code_lines[0]]
            
            base_indent_str = ' ' * (indentation_level * effective_indent_size)
            base_indent_len = len(base_indent_str)
            
            for line in code_lines[1:]:
                if line.startswith(base_indent_str):
                    dedented_source_code.append(line[base_indent_len:])
                else:
                    dedented_source_code.append(line)
            source_code = "\n".join(dedented_source_code)
        else:
            source_code = code_lines[0] if code_lines else ""
        
        # 重新解析代码片段
        parsed_tree = self.parser.parse(bytes(source_code, "utf8"))
        module_node = parsed_tree.root_node

        # 找到相对位置定义节点, 相当于重新解包装
        rel_src_node = module_node # 默认值
        if module_node.children:
            # 通常，我们关心的节点是 module 的第一个直接子节点
            first_child = module_node.children[0]
            if first_child.type in ['function_definition', 'class_definition', 'decorated_definition']:
                rel_src_node = first_child
            
        return CodeEntity(
            file_path=file_path,
            full_content=open(file_path, 'r').read(),
            indent_level=indentation_level,
            indent_size=effective_indent_size,
            line_end=end_line,
            line_start=start_line,
            src_code=source_code,
            src_node=node,
            rel_src_node=rel_src_node,
            complexity=1,
            name=name,
            code_type=code_type,
            strip_body=None,
            signature=None,
            filter_results=None,
            file_extension=file_extension,
            hash_code=generate_hash(source_code)
        )

    def extract_node_info(self, file_content: str, file_path: str) -> List[Dict[str, Node]]:
        try:
            # Step 1: capture all nodes
            tree = self.parser.parse(bytes(file_content, "utf8"))
            query_cursor = QueryCursor(self.entity_query)
            captures = query_cursor.captures(tree.root_node)

            info_map = {}
            
            # Step 2: Process all captured definition nodes first.
            for capture_name, node_list in captures.items():
                for node in node_list:
                    if capture_name in ['entity.function', 'entity.class']:
                        # This is a definition node
                        def_node = node
                        if def_node.id not in info_map:
                            info_map[def_node.id] = {}
                        info_map[def_node.id]['node'] = def_node
                        info_map[def_node.id]['type'] = 'function' if capture_name == 'entity.function' else 'class'
                    elif capture_name == 'entity.name':
                        # This is a name node. Associate it with its parent definition.
                        parent_def_node = node.parent
                        if parent_def_node:
                            if parent_def_node.id not in info_map:
                                info_map[parent_def_node.id] = {'node': parent_def_node}
                            info_map[parent_def_node.id]['name'] = node.text.decode('utf8')

            # Filter out any entries that failed to get a name
            return [info for info in info_map.values() if 'name' in info and 'node' in info]
        except Exception as e:
            print(f"Warning: Could not process file '{file_path}'. Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc() 
            return []


    def calculate_complexity(self, code_entity: CodeEntity) -> int:
        """
        Calculates the complexity of a code entity using a tree-sitter query.
        Complexity is 1 + the number of captured complexity points.
        """
        node = code_entity.src_node
        complexity = 1
        if not node:
            return complexity
        try:
            query_cursor = QueryCursor(self.complexity_query)
            captures = query_cursor.captures(node)
            for capture_name, node_list in captures.items():
                complexity += len(node_list)
            return complexity
        except Exception:
            return complexity

    def strip_function_body(self, entity: CodeEntity) -> Optional[str]:
        """
        Reconstructs the function/method, replacing its body with a placeholder,
        while preserving the signature and docstring. This method is robust as it
        rebuilds the code from the CST nodes rather than relying on byte offsets.
        """
        try:
            function_node = entity.src_node

            # Step 1: Identify the body node.
            body_node = function_node.child_by_field_name('body')
            if not body_node:
                print(f"Warning: Could not find a body node for entity '{entity.name}'.")
                return None

            # Step 2: Reconstruct the signature part by collecting text from all non-body child nodes.
            # The signature consists of all children of the function_node that appear *before* the body_node.
            signature_parts = []
            for child in function_node.children:
                if child.id == body_node.id:
                    # We've reached the body, stop collecting signature parts.
                    break
                signature_parts.append(child.text.decode('utf8'))
            
            # Join the parts to form the complete signature string.
            # We add a space between parts for good measure, then clean up.
            signature_text = " ".join(signature_parts)
            # Clean up potential double spaces or weird formatting from joining.
            signature_text = ' '.join(signature_text.split())
            
            # Step 3: Detect and extract the docstring text, if it exists.
            docstring_text = ""
            if body_node.named_child_count > 0:
                first_child = body_node.named_children[0]
                if first_child.type == 'expression_statement' and \
                first_child.child(0) and first_child.child(0).type == 'string':
                    # Get the full text of the docstring node.
                    docstring_text = first_child.text.decode('utf8')

            # Step 4: Prepare the placeholder with correct indentation.
            placeholder_text = self.placeholder_body
            # The placeholder's indent is one level deeper than the function's own indent.
            # indent_str = ' ' * (entity.indent_level * entity.indent_size + self.indent_size
            indent_str = ' ' * self.indent_size

            # Step 5: Assemble the final stripped function.
            
            # Start with the function's own indentation.
            # base_indent = ' ' * (entity.indent_level * entity.indent_size)
            base_indent = ''
            
            # Start building the final code string.
            final_parts = [base_indent + signature_text]
            
            if docstring_text:
                # If docstring exists, add it with correct indentation.
                # The docstring node text already contains its own internal newlines.
                final_parts.append(indent_str + docstring_text)
            
            # Add the placeholder.
            final_parts.append(indent_str + placeholder_text)

            return signature_text, "\n".join(final_parts) + '\n'

        except Exception as e:
            print(f"Error stripping function body for entity '{entity.name}': {e}")
            import traceback
            traceback.print_exc()
            return None

    def extract_entities(self, file_content: str, file_path: str, file_extension: str) -> List[CodeEntity]:
        entities = []
        # step 1: extract nodes
        node_info_list = self.extract_node_info(file_content, file_path)
        if len(node_info_list) > 100:
            node_info_list = node_info_list[: 100]
        # step 2: trans node to entity
        for node_info in node_info_list:
            try:
                node, name, code_type = node_info['node'], node_info['name'], node_info['type']
            except KeyError as e:
                continue
            entity = self.get_entity_from_node(node, name, code_type, file_content, file_path, self.indent_size, file_extension)
            entities.append(entity)
        # step 3: cal entity complexity
        for entity in entities:
            complexity = self.calculate_complexity(entity)
            entity.complexity = complexity
        # step 4: strip function body
        for entity in entities:
            if entity.code_type != 'function':
                continue
            signature, strip_body = self.strip_function_body(entity)
            entity.signature = signature
            entity.strip_body = strip_body
        # step 5: get filter result
        for entity in entities:
            filter_results = self.filter_manager.get_entity_filter_result(entity)
            entity.filter_results = filter_results
        return entities


def init_all_processor(language_config_dict) -> dict:
    processor_map = {}
    for language_name, config in language_config_dict.items():
        print('Init Language Processor:', config.NAME)
        processor = LanguageProcessor(
            language=config.LANGUAGE,
            entity_query_string=config.ENTITY_QUERY,
            complexity_query_string=config.COMPLEXITY_QUERY,
            filter_queries=config.FILTER_QUERIES,
            placeholder_body=config.PLACEHOLDER_BODY,
            indent_size=config.INDENT_SIZE,
            file_extensions=config.FILE_EXTENSIONS,
            file_patterns=config.FILE_PATTERNS,
            language_name=config.NAME.lower()
        )
        for extension in config.FILE_EXTENSIONS:
            processor_map[extension] = processor
    return processor_map


def extract_entities_from_directory(
    directory_path: str,
    language_config_dict: dict,
    exclude_tests: bool = True,
    max_entities: int = -1,
) -> list[CodeEntity]:
    """
    Extracts entities from files in a directory using a specific language processor.
    """
    # init processor from config
    processor_map = init_all_processor(language_config_dict)
    all_entities = []

    for root, _, files in os.walk(directory_path):
        for file in files:
            print('processing', file)
            # 1. 检查后缀，获取处理器
            _, file_extension = os.path.splitext(file)
            if not file_extension:
                continue            
            processor = processor_map.get(file_extension)
            if processor is None:
                continue
            # 2. 过滤单元测试
            test_patterns = processor.get_test_file_patterns()
            if exclude_tests and any([x in root for x in test_patterns]):
                continue
            
            # 3. 获取文件内容
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
            except Exception:
                continue

            # 4. 委托给处理器进行解析和提取
            entities_in_file = processor.extract_entities(file_content, file_path, file_extension)
            all_entities.extend(entities_in_file)

            if max_entities != -1 and len(all_entities) >= max_entities:
                return all_entities
    return all_entities