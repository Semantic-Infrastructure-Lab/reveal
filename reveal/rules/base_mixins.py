"""Mixins for reveal's rule system.

Provides reusable functionality that can be mixed into rule classes
to reduce boilerplate and ensure consistent behavior.
"""

import ast
import functools
import logging
from typing import Optional

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=4)
def _cached_treesitter_parse(content: str, file_path: str, language: str):
    """Parse non-Python content into a tree-sitter root node, LRU-cached.

    Keyed by (content, file_path, language) — same rationale as
    ``_cached_ast_parse``. Returns None on any parse failure (unknown
    language, grammar not installed, etc.) rather than raising, so callers
    can use the same "skip" pattern as the Python AST mixin.
    """
    try:
        from tree_sitter_language_pack import get_parser

        from ..core import ts_parse, tree_root
    except ImportError as e:
        logger.warning(f"tree-sitter unavailable for {file_path}: {e}")
        return None
    try:
        parser = get_parser(language)  # type: ignore[arg-type]
        tree = ts_parse(parser, content)
        return tree_root(tree)
    except Exception as e:
        logger.warning(f"tree-sitter parse failed for {file_path} ({language}): {e}")
        return None


@functools.lru_cache(maxsize=4)
def _cached_ast_parse(content: str, file_path: str) -> Optional[ast.AST]:
    """Parse Python content into AST with LRU cache.

    Keyed by (content, file_path) so the same file processed by multiple
    rules in one check_file() call hits the cache instead of re-parsing.
    maxsize=4 keeps memory bounded while covering all rules on one file.
    """
    try:
        return ast.parse(content, filename=file_path)
    except SyntaxError as e:
        logger.warning(f"AST parse failed (syntax error) for {file_path}: {e}")
        return None
    except Exception as e:
        logger.warning(f"AST parse failed for {file_path}: {e}")
        return None


class ASTParsingMixin:
    """Mixin for rules that need to parse Python AST.

    Provides safe AST parsing with consistent error handling.
    Rules can inherit from both BaseRule and this mixin.

    Example:
        class B001(BaseRule, ASTParsingMixin):
            def check(self, file_path, structure, content):
                tree = self._parse_python(content, file_path)
                if tree is None:
                    return []  # Syntax error, skip
                # ... use tree
    """

    def _parse_python(self, content: str, file_path: str = "<unknown>") -> Optional[ast.AST]:
        """Parse Python content into AST.

        Uses module-level LRU cache so multiple rules processing the same
        file share one parsed AST instead of each re-parsing independently.

        Args:
            content: Python source code
            file_path: Path for error messages (default: "<unknown>")

        Returns:
            AST tree if parsing succeeds, None on SyntaxError
        """
        return _cached_ast_parse(content, file_path)

    def _ast_walk(self, tree: ast.AST) -> list:
        """Return all AST nodes as a flat list, caching on the tree object.

        The first call for a given tree builds the list once; subsequent calls
        (from other rules processing the same file) return the cached list.
        Since all rules on one file receive the same cached tree object from
        _cached_ast_parse, this eliminates 5 of 6 redundant ast.walk traversals.

        Use instead of ``ast.walk(tree)`` in rule check() methods.
        """
        try:
            return list(tree._cached_walk)  # type: ignore[attr-defined]
        except AttributeError:
            nodes = list(ast.walk(tree))
            tree._cached_walk = nodes  # type: ignore[attr-defined]
            return nodes

    def _parse_python_or_skip(self, content: str, file_path: str = "<unknown>") -> tuple[Optional[ast.AST], list]:
        """Parse Python or return empty detections list.

        Convenience method for common pattern in check() methods.

        Args:
            content: Python source code
            file_path: Path for error messages

        Returns:
            Tuple of (tree, detections) where:
            - tree is AST or None
            - detections is empty list (for early return on parse failure)

        Example:
            def check(self, file_path, structure, content):
                tree, detections = self._parse_python_or_skip(content, file_path)
                if tree is None:
                    return detections
                # ... analyze tree
        """
        tree = self._parse_python(content, file_path)
        return tree, []


class TreeSitterParsingMixin:
    """Mixin for rules that need to parse non-Python content via tree-sitter.

    Companion to ASTParsingMixin (which is Python/`ast`-only). A rule using
    this mixin owns its own extension→language mapping (it already needs
    one to set ``file_patterns``), and passes the language explicitly —
    this mixin only owns the parse-and-cache mechanics, not language
    detection, matching how the rest of reveal's rule layer stays
    unopinionated about any one language.

    Example:
        class B006(BaseRule, ASTParsingMixin, TreeSitterParsingMixin):
            _CS_LANGUAGE = 'csharp'

            def check(self, file_path, structure, content):
                if file_path.endswith('.cs'):
                    root, detections = self._parse_treesitter_or_skip(
                        content, file_path, self._CS_LANGUAGE)
                    if root is None:
                        return detections
                    for node in self._ts_walk(root):
                        ...
    """

    def _parse_treesitter(self, content: str, file_path: str, language: str):
        """Parse content with tree-sitter, returning the root node or None."""
        return _cached_treesitter_parse(content, file_path, language)

    def _parse_treesitter_or_skip(self, content: str, file_path: str, language: str) -> tuple:
        """Parse or return empty detections list, mirroring _parse_python_or_skip.

        Returns:
            Tuple of (root_node, detections) where root_node is None on
            parse failure and detections is an empty list (for early
            return on parse failure).
        """
        return self._parse_treesitter(content, file_path, language), []

    def _ts_walk(self, root) -> list:
        """Return every node in the tree rooted at `root`, pre-order.

        No node-object caching (unlike `_ast_walk`) — tree-sitter 1.x Node
        objects don't support arbitrary attribute assignment. Fine as long
        as only one rule per language consumes a given tree; revisit with a
        (content, file_path, language)-keyed cache if a second consumer
        shows up.
        """
        if root is None:
            return []
        from ..core import iter_tree
        return list(iter_tree(root))

    def _ts_node_text(self, node, content_bytes: bytes) -> str:
        """Return the source text spanned by a tree-sitter node."""
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8', errors='replace')
