"""Document and patch generation utilities."""

from nl2repo.generators.patch_generator import (
    PatchGenerator,
    apply_batch_entities_in_pool,
    gen_module_patches_parallel,
)
from nl2repo.generators.tree_generator import (
    generate_tree_structure,
    TreeGenerator,
)
from nl2repo.generators.doc_builder import (
    DocBuilder,
    build_full_doc,
)

__all__ = [
    # Patch generation
    "PatchGenerator",
    "apply_batch_entities_in_pool",
    "gen_module_patches_parallel",
    # Tree generation
    "generate_tree_structure",
    "TreeGenerator",
    # Document building
    "DocBuilder",
    "build_full_doc",
]