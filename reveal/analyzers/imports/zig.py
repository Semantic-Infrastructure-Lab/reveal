"""Zig import extraction using tree-sitter.

BACK-514: Zig's ``@import("x")`` is a builtin-call token
(``BUILTINIDENTIFIER``) with a sibling ``FnCallArguments``, structurally
unlike both the dedicated-import-node and the call-node-wrapping-an-identifier
shapes ``generic.py``'s ``_ImportSpec`` models — bolting a fourth mode onto
that dataclass for one language would be designing the shared abstraction
around a single instance. Zig joins python.py/javascript.py/go.py/rust.py as a
small bespoke ``LanguageExtractor`` instead.

Node kinds verified by direct parse (2026-07-09, session apricot-tapestry-0709):
``@import("std")`` parses as
``ErrorUnionExpr > SuffixExpr > [BUILTINIDENTIFIER '@import', FnCallArguments]``,
with the string literal nested inside ``FnCallArguments`` as
``ErrorUnionExpr > SuffixExpr > STRINGLITERALSINGLE``.
"""

import logging
from pathlib import Path
from typing import List, Optional, Set

from ...core import node_children as _children
from ...registry import get_analyzer
from .base import LanguageExtractor, register_extractor
from .types import ImportStatement

logger = logging.getLogger(__name__)


def _line_text(analyzer, line_number: int) -> str:
    idx = line_number - 1
    if 0 <= idx < len(analyzer.lines):
        return analyzer.lines[idx].rstrip()
    return ""


@register_extractor
class ZigImportExtractor(LanguageExtractor):
    """Zig ``@import("...")`` extractor using pure tree-sitter parsing.

    Supports:
    - Stdlib/package imports: ``@import("std")``, ``@import("builtin")``
    - Relative file imports: ``@import("foo.zig")``
    """

    extensions = {'.zig'}
    language_name = 'Zig'

    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return []
            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return []
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("extract_imports failed for %s: %s", file_path, e)
            return []

        imports: List[ImportStatement] = []
        for node in analyzer._find_nodes_by_type('BUILTINIDENTIFIER'):
            if analyzer._get_node_text(node) != '@import':
                continue
            stmt = self._builtin_call_to_import(node, analyzer, file_path)
            if stmt is not None:
                imports.append(stmt)

        imports.sort(key=lambda s: s.line_number)
        return imports

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Not implemented — imports set ``skip_unused=True``."""
        return set()

    def _builtin_call_to_import(self, node, analyzer, file_path: Path) -> Optional[ImportStatement]:
        """Turn a ``@import`` BUILTINIDENTIFIER node into an ImportStatement.

        The sibling ``FnCallArguments`` (under the shared ``SuffixExpr``
        parent) holds the string-literal argument. Non-string-literal args
        (impossible in valid Zig, but be defensive) are skipped.
        """
        parent = node.parent()
        if parent is None:
            return None

        args_node = None
        for child in _children(parent):
            if child.kind() == 'FnCallArguments':
                args_node = child
                break
        if args_node is None:
            return None

        literal = self._first_descendant_text(args_node, analyzer, ('STRINGLITERALSINGLE',))
        if not literal:
            return None
        module = literal.strip('"')
        if not module:
            return None

        return ImportStatement(
            file_path=file_path,
            line_number=node.start_position().row + 1,
            module_name=module,
            imported_names=[],
            is_relative=module.startswith('.') or module.endswith('.zig'),
            import_type='import',
            alias=None,
            source_line=_line_text(analyzer, node.start_position().row + 1),
            skip_unused=True,
        )

    @staticmethod
    def _first_descendant_text(node, analyzer, kinds) -> Optional[str]:
        stack = list(reversed(_children(node)))
        while stack:
            cur = stack.pop()
            if cur.kind() in kinds:
                return analyzer._get_node_text(cur)
            stack.extend(reversed(_children(cur)))
        return None

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
    ) -> Optional[Path]:
        """Resolve ``@import("foo.zig")`` to a real in-tree file.

        Only string literals ending in ``.zig`` are file targets; stdlib/
        package names (``std``, ``builtin``, a build-graph module alias) have
        no single backing file and are honestly skipped, never fabricated.
        """
        module = stmt.module_name
        if not module.endswith('.zig'):
            return None

        roots = [base_path] + list(search_paths or [])
        for root in roots:
            candidate = (root / module).resolve()
            if candidate.is_file():
                return candidate
        return None


__all__ = ['ZigImportExtractor']
