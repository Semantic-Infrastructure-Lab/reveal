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
def _cached_ast_parse(content: str, file_path: str) -> Optional[ast.AST]:
    """Parse Python content into AST with LRU cache.

    Keyed by (content, file_path) so the same file processed by multiple
    rules in one check_file() call hits the cache instead of re-parsing.
    maxsize=4 keeps memory bounded while covering all rules on one file.
    """
    try:
        return ast.parse(content, filename=file_path)
    except SyntaxError as e:
        logger.debug(f"Syntax error in {file_path}: {e}")
        return None
    except Exception as e:
        logger.debug(f"Failed to parse {file_path}: {e}")
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
            return tree._cached_walk  # type: ignore[attr-defined]
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
