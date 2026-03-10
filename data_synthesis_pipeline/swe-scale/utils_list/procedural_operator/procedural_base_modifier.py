import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import random
from typing import *
from tree_sitter import Language, Parser, Query, QueryCursor, Node
from utils_list.data_structure.base_data_structure import CodeEntity


Edit = Tuple[int, int, bytes]

class BaseTreeSitterModifier:
    name = 'BaseTreeSitterModifier'
    explanation = 'BaseTreeSitterModifier'
    query_key = 'BaseTreeSitterModifier'

    def __init__(self, 
        language_name: str,
        language: Language,
        modification_querise: dict,
        language_syntax_dict: dict,
        likelihood: float = 1,
        seed: float = 42, 
        min_complexity_threshold: int = 10,
        max_complexity_threshold: int = 10,
    ):
        assert 0 <= likelihood <= 1, "Likelihood must be between 0 and 1."
        self.rand = random.Random(seed)
        self.likelihood = likelihood
        self.language_name = language_name
        self.language = language
        self.min_complexity_threshold = min_complexity_threshold
        self.max_complexity_threshold = max_complexity_threshold
        self.modification_querise = modification_querise
        self.language_syntax_dict = language_syntax_dict
        self.compiled_queries: Dict[str, Query] = self._compile_queries(modification_querise)
    
    def _compile_queries(self, filter_queries: Dict[str, str]) -> Dict[str, Query]:
        compiled_queries = {}
        for key, query_str in self.modification_querise.items():
            if query_str:
                # try:
                compiled_queries[key] = Query(self.language, query_str)
                # except Exception as e:
                #     print(f"Warning: Could not compile query for key '{key}'. Query: '{query_str}'. Error: {e}")
        return compiled_queries 

    def flip(self) -> bool:
        return self.rand.random() < self.likelihood

    def apply(self, entity: CodeEntity) -> str:
        try:
            query = self.compiled_queries.get(self.query_key, None)
            if not query:
                print(f"Warning: No query found for key '{self.query_key}' in language '{self.language_name}'")
                raise ValueError(f"Error in {self.name}. No query found for key '{self.query_key}' in language '{self.language_name}'")
            query_cursor = QueryCursor(query)
            matches = query_cursor.matches(entity.rel_src_node)

            source_bytes = bytes(entity.src_code, "utf8")
            all_edits: List[Edit] = []
            for _pattern_index, captures_dict in matches:
                if not self.flip():
                    continue                  
                edits = self._compute_edits(captures_dict, source_bytes)
                if edits:
                    all_edits.extend(edits)

            if not all_edits:
                return entity.src_code

            new_source_bytes = bytearray(source_bytes)
            for start_byte, end_byte, replacement_bytes in sorted(all_edits, key=lambda e: e[0], reverse=True):
                new_source_bytes[start_byte:end_byte] = replacement_bytes
            return bytes(new_source_bytes).decode('utf-8')
        except Exception as e:
            return entity.src_code

    def _compute_edits(self, captures: Dict[str, Node], source_bytes: bytes) -> List[Edit] | None:
        raise NotImplementedError

    def _get_matches(self, entity: CodeEntity):
        raise NotImplementedError

    def condition(self, entity: CodeEntity) -> bool:
        raise NotImplementedError
