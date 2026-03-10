import yaml
import textwrap
import tree_sitter_c as tsc
import tree_sitter_c_sharp as tscs
import tree_sitter_cpp as tscpp
import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjs
import tree_sitter_php as tsphp
import tree_sitter_python as tspy
import tree_sitter_ruby as tsruby
import tree_sitter_rust as tsrs
import tree_sitter_typescript as tsts
from tree_sitter import Language
from typing import *


class LanguageConfig:
    def __init__(self, config_data: Dict[str, Any]):
        # 1. base attribute
        self.NAME: str = config_data['name']
        self.LANGUAGE: Language = self.tree_sitter_language_map(config_data['name'])
        self.PLACEHOLDER_BODY: str = config_data['placeholder_body']
        self.INDENT_SIZE: int = config_data['indent_size']
        self.FILE_EXTENSIONS: Set[str] = set(config_data['file_extensions'])
        self.FILE_PATTERNS: Set[str] = set(config_data['file_patterns'])

        # 2. base queries config
        self.ENTITY_QUERY: str = config_data['queries']['entity_query']
        self.COMPLEXITY_QUERY: str = config_data['queries']['complexity_query']
        self.FILTER_QUERIES: Dict[str, str] = config_data['queries']['filters_query']
        
        # 3. modifier config
        self.MODIFICATION_QUERIES: Dict[str, str] = {}
        for category in config_data['queries']['modifiers'].values():
            for key, value in category.items():
                self.MODIFICATION_QUERIES[key.upper()] = value
        
        # 4. language special syntax
        self.LANGUAGE_SYNTAX_DICT = {
            'CHANGE_OPERATORS_GROUPS': config_data['queries']['change_operators_groups'],
            'FLIPPED_OPERATORS': config_data['queries']['flipped_operators'],
            'CHANGE_CONSTANTS_VALID_PARENTS': config_data['queries']['change_constants_valid_parents'],
            'FUNCTION_CONTEXT_TYPES': config_data['queries']['function_context_types'],
            'SHUFFLE_LINES_BLACKLIST': config_data['queries']['shuffle_lines_blacklist'],
        }

    def tree_sitter_language_map(self, language: str):
        if language.lower() == 'python':
            return Language(tspy.language())
        elif language.lower() == 'javascript':
            return Language(tsjs.language())
        elif language.lower() == 'typescript':
            return Language(tsts.language_typescript())
        elif language.lower() == 'tsx':
            return Language(tsts.language_tsx())
        else:
            raise ValueError
        return


def get_all_language_config():
    language_yaml_list = [
        '/mnt/cfs_bj_mt/workspace/zengyucheng/workdir/workdir_for_swe_smith/zzz_rebuild_swe_smith/qianfan_coder_smith/utils_list/language_config/language_python_config.yaml',
        '/mnt/cfs_bj_mt/workspace/zengyucheng/workdir/workdir_for_swe_smith/zzz_rebuild_swe_smith/qianfan_coder_smith/utils_list/language_config/language_javascript_config.yaml',
        '/mnt/cfs_bj_mt/workspace/zengyucheng/workdir/workdir_for_swe_smith/zzz_rebuild_swe_smith/qianfan_coder_smith/utils_list/language_config/language_typescript_config.yaml'
    ]
    config_map = {}
    for language_yaml in language_yaml_list:
        with open(language_yaml, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        config = LanguageConfig(config_data)
        config_map[config_data['name'].lower()] = config
    return config_map


if __name__ == '__main__':
    get_all_language_config()
    