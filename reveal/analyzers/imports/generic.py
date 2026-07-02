"""Data-driven import extraction for tree-sitter languages without a bespoke extractor.

Bespoke extractors (python.py, javascript.py, go.py, rust.py) hand-parse each
language's import grammar and resolve modules to files. That is a lot of code
per language, which is why only four existed — while IMPORTS_ADAPTER_GUIDE.md
advertised "✅ Full" support for ten. The gap showed up in dogfooding: `imports://`
returned a silent ``Total Files: 0`` for C, C++, C#, Java, PHP, and Ruby, which
reads as "clean" rather than "not scanned".

This module closes that gap the same way ``calls://`` already handles many
languages from one walker: a small per-language data table (:class:`_ImportSpec`)
naming the tree-sitter node kinds that *are* import statements, plus the leading
keyword tokens to strip. One generic walker turns each matching node into an
:class:`ImportStatement`. Adding a language is a table row and a three-line
subclass — no new parsing logic.

Scope (honest about what this delivers):
  * **Listing** of import statements for all covered languages — the primary fix
    for the silent-zero bug.
  * **File-level dependency edges** (``?circular``, fan-in) for C/C++ only, where
    ``#include "header.h"`` resolves cleanly to a sibling/searched file. Angle-bracket
    system includes (``<stdio.h>``) are intentionally not resolved.
  * **Unused-import detection is not claimed** for these languages — the imports
    are flagged ``skip_unused`` so they are never falsely reported as unused
    (textual ``#include`` and namespace/require imports lack reliable
    symbol-usage semantics without per-language work).

Verified node kinds against tree-sitter-language-pack 1.8.x real parses
(2026-07-02, session ancient-mission-0702).
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, FrozenSet, List, Optional, Set

from ...core import node_children as _children
from ...defaults import SKIP_DIRECTORIES
from ...registry import get_analyzer
from .base import LanguageExtractor, register_extractor
from .types import ImportStatement

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ImportSpec:
    """Per-language description of how imports appear in the tree-sitter grammar.

    Attributes:
        import_node_types: Node ``kind()`` values that represent a dedicated
            import statement (e.g. ``preproc_include``, ``import_declaration``).
        keywords: Leading whitespace-delimited tokens to strip from a node's
            source text before reading the module path (e.g. ``import``,
            ``using``, ``static``, ``#include``).
        call_import_names: For languages that express imports as ordinary calls
            (Ruby ``require 'json'``), the callee names that count as imports.
            Nodes of kind ``call`` are matched only when their first token is in
            this set. Empty for languages with dedicated import nodes.
        alias_assignment: True when ``ALIAS = MODULE`` syntax assigns an alias
            (C#/C++ ``using X = Y``). The token left of ``=`` becomes the alias,
            the right side the module.
        resolve_includes: True when quoted paths should resolve to actual files
            for the dependency graph (C/C++ ``#include "foo.h"``).
    """

    import_node_types: FrozenSet[str]
    keywords: FrozenSet[str]
    call_import_names: FrozenSet[str] = field(default_factory=frozenset)
    alias_assignment: bool = False
    resolve_includes: bool = False


class _GenericTreeSitterImportExtractor(LanguageExtractor):
    """Extract imports for one language from a data-driven :class:`_ImportSpec`.

    Subclasses set ``extensions``, ``language_name``, and ``spec``. All parsing
    behaviour is inherited; there is no per-language code.
    """

    # Subclasses MUST set these.
    spec: ClassVar[_ImportSpec]

    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []

        imports: List[ImportStatement] = []

        for node_type in self.spec.import_node_types:
            for node in analyzer._find_nodes_by_type(node_type):
                stmt = self._node_to_import(node, analyzer, file_path)
                if stmt is not None:
                    imports.append(stmt)

        # Call-style imports (Ruby require/require_relative/load).
        if self.spec.call_import_names:
            for node in analyzer._find_nodes_by_type('call'):
                stmt = self._call_to_import(node, analyzer, file_path)
                if stmt is not None:
                    imports.append(stmt)

        imports.sort(key=lambda s: s.line_number)
        return imports

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Not implemented for generic languages.

        Symbol-usage extraction (for unused-import detection) needs
        per-language semantics we do not claim here. Imports produced by this
        extractor set ``skip_unused=True`` so they are never falsely flagged.
        """
        return set()

    # --- internals -------------------------------------------------------

    @staticmethod
    def _get_analyzer(file_path: Path):
        """Instantiate the tree-sitter analyzer for a file, or None on failure."""
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return None
            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return None
            return analyzer
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("generic import analyzer failed for %s: %s", file_path, e)
            return None

    def _node_to_import(self, node, analyzer, file_path: Path) -> Optional[ImportStatement]:
        """Turn a dedicated import-statement node into an ImportStatement."""
        raw = analyzer._get_node_text(node)
        return self._build(raw, node, file_path)

    def _call_to_import(self, node, analyzer, file_path: Path) -> Optional[ImportStatement]:
        """Turn a ``require``-style call node into an ImportStatement, if it is one.

        Reads the call structurally (callee identifier + string argument) so both
        ``require 'json'`` and ``require('json')`` are recognised, and nested
        calls like ``puts(require_relative 'x')`` are ignored unless they are the
        callee themselves.
        """
        callee = None
        for child in _children(node):
            if child.kind() == 'identifier':
                callee = analyzer._get_node_text(child)
                break
        if callee is None or callee not in self.spec.call_import_names:
            return None

        module = self._first_descendant_text(node, analyzer, ('string_content',))
        if not module:
            # Fall back to the whole string literal, minus quotes.
            literal = self._first_descendant_text(node, analyzer, ('string',))
            module = literal.strip('"\'') if literal else ''
        if not module:
            return None

        return ImportStatement(
            file_path=file_path,
            line_number=node.start_position().row + 1,
            module_name=module,
            imported_names=[],
            is_relative=module.startswith('.'),
            import_type='import',
            alias=None,
            source_line=analyzer._get_node_text(node).strip(),
            skip_unused=True,
        )

    @staticmethod
    def _first_descendant_text(node, analyzer, kinds) -> Optional[str]:
        """DFS pre-order: text of the first descendant whose kind is in *kinds*."""
        stack = list(reversed(_children(node)))
        while stack:
            cur = stack.pop()
            if cur.kind() in kinds:
                return analyzer._get_node_text(cur)
            stack.extend(reversed(_children(cur)))
        return None

    def _build(self, raw: str, node, file_path: Path) -> Optional[ImportStatement]:
        """Parse cleaned source text into an ImportStatement (data-driven)."""
        source_line = raw.strip()
        # Collapse whitespace/newlines and drop a trailing ';'.
        text = ' '.join(source_line.split())
        if text.endswith(';'):
            text = text[:-1].rstrip()

        had_angle = '<' in text and '>' in text  # C system include marker

        # Strip leading keyword tokens (import / using / static / #include / ...).
        tokens = text.split(' ')
        while tokens and tokens[0] in self.spec.keywords:
            tokens.pop(0)
        remainder = ' '.join(tokens).strip()
        if not remainder:
            return None

        alias: Optional[str] = None

        # `Module as Alias` (Java/PHP/Python-style).
        if ' as ' in remainder:
            remainder, alias = (p.strip() for p in remainder.split(' as ', 1))
        # `Alias = Module` (C#/C++ using-alias).
        elif self.spec.alias_assignment and '=' in remainder:
            left, right = remainder.split('=', 1)
            alias = left.strip()
            remainder = right.strip()

        # Strip surrounding quotes always; strip angle brackets only for C/C++
        # includes (avoid mangling e.g. C# `using X = List<int>` generics).
        strip_chars = '"\' '
        if self.spec.resolve_includes:
            strip_chars += '<>'
        module_name = remainder.strip(strip_chars)
        if not module_name:
            return None

        is_system_include = had_angle and self.spec.resolve_includes
        # Relative when it's a quoted local include, or an explicit ./.. path.
        is_relative = (
            (self.spec.resolve_includes and not is_system_include)
            or module_name.startswith('.')
        )

        return ImportStatement(
            file_path=file_path,
            line_number=node.start_position().row + 1,
            module_name=module_name,
            imported_names=[],
            is_relative=is_relative,
            import_type='include' if self.spec.resolve_includes else 'import',
            alias=alias,
            source_line=source_line,
            skip_unused=True,
        )

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
    ) -> Optional[Path]:
        """Resolve a quoted C/C++ ``#include`` to a real file (for the dep graph).

        System includes (``<stdio.h>``) and non-include languages return None —
        their file-level graph is not claimed. Quoted includes are looked up
        next to the including file first, then under each project search path.
        """
        # System includes (is_relative=False) and non-include languages are not
        # resolved — their file-level graph is not claimed.
        if not self.spec.resolve_includes or not stmt.is_relative:
            return None

        target = stmt.module_name
        # 1. Sibling of the including file (the common case in flat C trees).
        candidate = (base_path / target).resolve()
        if candidate.is_file():
            return candidate

        # 2. Under each project search path (root, then full-suffix path match).
        target_parts = Path(target).parts
        n = len(target_parts)
        for root in search_paths or []:
            candidate = (root / target).resolve()
            if candidate.is_file():
                return candidate
            if not root.is_dir():
                continue
            if n == 1:
                # Bare basename target (no qualifying directory) — bounded
                # one-level match, same as before (BACK-398).
                basename = target_parts[0]
                for child in root.iterdir():
                    if child.is_dir():
                        sub = (child / basename).resolve()
                        if sub.is_file():
                            return sub
                continue
            # BACK-404: match the candidate's full trailing path against every
            # directory component of the quoted target (e.g. "jemalloc/internal/
            # util.h"), not just its basename — a basename-only match collides
            # across vendored subtrees that happen to share a common header
            # name (util.h, config.h, types.h, ...).
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in SKIP_DIRECTORIES and not d.startswith('.')
                ]
                for fname in filenames:
                    candidate = Path(dirpath) / fname
                    if candidate.parts[-n:] == target_parts:
                        return candidate.resolve()
        return None


# --- Language specs + registered subclasses ------------------------------
#
# Each subclass is three lines. Adding a language = add a spec + subclass.

_C_SPEC = _ImportSpec(
    import_node_types=frozenset({'preproc_include'}),
    keywords=frozenset({'#include'}),
    resolve_includes=True,
)

_CPP_SPEC = _ImportSpec(
    # C++20 `import mod;` is `import_declaration`; rare but cheap to include.
    import_node_types=frozenset({'preproc_include', 'import_declaration'}),
    keywords=frozenset({'#include', 'import'}),
    resolve_includes=True,
)

_JAVA_SPEC = _ImportSpec(
    import_node_types=frozenset({'import_declaration'}),
    keywords=frozenset({'import', 'static'}),
)

_CSHARP_SPEC = _ImportSpec(
    import_node_types=frozenset({'using_directive'}),
    keywords=frozenset({'using', 'global', 'static'}),
    alias_assignment=True,
)

_PHP_SPEC = _ImportSpec(
    import_node_types=frozenset({
        'namespace_use_declaration',
        'require_expression',
        'require_once_expression',
        'include_expression',
        'include_once_expression',
    }),
    keywords=frozenset({
        'use', 'function', 'const',
        'require', 'require_once', 'include', 'include_once',
    }),
)

_RUBY_SPEC = _ImportSpec(
    import_node_types=frozenset(),  # no dedicated node — matched as calls
    keywords=frozenset({'require', 'require_relative', 'load'}),
    call_import_names=frozenset({'require', 'require_relative', 'load'}),
)


@register_extractor
class CImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.c', '.h'}
    language_name = 'C'
    spec = _C_SPEC


@register_extractor
class CppImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.cpp', '.cc', '.cxx', '.hpp', '.hxx'}
    language_name = 'C++'
    spec = _CPP_SPEC


@register_extractor
class JavaImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.java'}
    language_name = 'Java'
    spec = _JAVA_SPEC


@register_extractor
class CSharpImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.cs'}
    language_name = 'C#'
    spec = _CSHARP_SPEC


@register_extractor
class PhpImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.php'}
    language_name = 'PHP'
    spec = _PHP_SPEC


@register_extractor
class RubyImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.rb'}
    language_name = 'Ruby'
    spec = _RUBY_SPEC


__all__ = [
    '_ImportSpec',
    '_GenericTreeSitterImportExtractor',
    'CImportExtractor',
    'CppImportExtractor',
    'JavaImportExtractor',
    'CSharpImportExtractor',
    'PhpImportExtractor',
    'RubyImportExtractor',
]
