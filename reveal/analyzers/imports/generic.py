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
  * **File-level dependency edges** (``?circular``, fan-in) for every language
    whose imports name an *in-tree file* structurally (BACK-487/488):
      - C/C++ — ``#include "header.h"`` → sibling/searched file. Angle-bracket
        system includes (``<stdio.h>``) are intentionally not resolved.
      - Java — ``import com.pkg.Type`` → ``com/pkg/Type.java`` (package==dir is
        guaranteed by javac, so the full path-suffix match is reliable).
      - PHP — ``use App\\Models\\User`` → ``.../Models/User.php`` (longest unique
        path-suffix, tolerant of the PSR-4 vendor-root prefix); ``require``/
        ``include`` string-literal paths → file relative to the including file.
      - Ruby — ``require_relative './x'`` → ``x.rb`` relative to the file;
        ``load 'config.rb'``/``require 'lib/thing.rb'`` when they name a real
        in-tree ``.rb``. Bare ``require 'json'`` (a gem) is correctly skipped.
      - Swift — ``import Foo`` → ``Foo.swift`` when a module maps 1:1 to a file.
      - Kotlin — ``import com.pkg.Bar`` → ``com/pkg/Bar.kt`` full-suffix.
    Every case resolves *only* to a file that exists in the tree; when the
    target is a package/namespace/gem with no single backing file (Java ``.*``
    wildcards, C# ``using`` of a multi-file namespace, unresolved PSR-4 prefixes)
    the import is **skipped, never fabricated** — same honest-skip contract the
    C/C++ angle-bracket case has always had.
  * **C# note**: ``using X.Y`` imports a *namespace* (a directory of files), not a
    single type, so it resolves a file only in the rare case a matching
    ``Y.cs`` exists — otherwise skipped. Full C# fan-in needs a
    namespace-declaration index (not filename matching); tracked separately.
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
from typing import ClassVar, Dict, FrozenSet, List, Optional, Set

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
            Nodes of kind ``call_node_type`` are matched only when their first
            token is in this set. Empty for languages with dedicated import nodes.
        call_node_type: The tree-sitter node ``kind()`` for a call expression.
            Defaults to ``'call'`` (Ruby, GDScript); Lua's grammar names it
            ``'function_call'`` instead.
        alias_assignment: True when ``ALIAS = MODULE`` syntax assigns an alias
            (C#/C++ ``using X = Y``). The token left of ``=`` becomes the alias,
            the right side the module.
        resolve_includes: True when quoted paths should resolve to actual files
            for the dependency graph (C/C++ ``#include "foo.h"``).
        module_separator: The character joining components of a qualified
            *type* import that maps to a file path — ``.`` for Java/C#/Kotlin
            (``com.pkg.Type`` → ``com/pkg/Type.ext``), ``\\`` for PHP
            (``App\\Models\\User``). ``None`` for languages whose imports are
            only ever path-style string literals (Ruby) or single-token module
            names (Swift ``import Foo``). Enables dotted-name file resolution
            (BACK-487/488).
        source_extensions: The source-file extension(s) an unqualified module
            name maps to when resolving edges — ``{'.java'}``, ``{'.rb'}``,
            ``{'.php'}``, ``{'.cs'}``, ``{'.kt'}``, ``{'.swift'}``. Empty means
            "listing only, no edge resolution" (the pre-BACK-487 default). A
            non-empty set is the master switch that turns on
            :meth:`_resolve_module`.
        project_relative_prefix: A URI-style prefix (GDScript ``'res://'``)
            that names a path relative to the *project root*, not the
            importing file. When set and a module starts with this prefix,
            resolution strips it and tries only ``search_paths`` (never
            ``base_path``-relative) — see :meth:`_resolve_module`.
    """

    import_node_types: FrozenSet[str]
    keywords: FrozenSet[str]
    call_import_names: FrozenSet[str] = field(default_factory=frozenset)
    call_node_type: str = 'call'
    alias_assignment: bool = False
    resolve_includes: bool = False
    module_separator: Optional[str] = None
    source_extensions: FrozenSet[str] = field(default_factory=frozenset)
    project_relative_prefix: Optional[str] = None


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

        # Call-style imports (Ruby require/require_relative/load; Lua require;
        # GDScript preload/load).
        if self.spec.call_import_names:
            for node in analyzer._find_nodes_by_type(self.spec.call_node_type):
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

    @staticmethod
    def _extract_include_target(remainder: str) -> Optional[str]:
        """Return the include target between the first `<..>` or `"..."` pair.

        Truncates at the first closing delimiter so a trailing comment
        (`<math.h> /* ... */`, `"x.h" // ...`) can't leak into the module name.
        Returns None if no delimited target is present (caller falls back).
        """
        for open_ch, close_ch in (('<', '>'), ('"', '"')):
            start = remainder.find(open_ch)
            if start == -1:
                continue
            end = remainder.find(close_ch, start + 1)
            if end != -1:
                return remainder[start + 1:end].strip()
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

        # For a C/C++ include, extract exactly what's between the delimiters —
        # `<...>` for a system include or `"..."` for a local one — up to the
        # *first* closing delimiter. A blanket .strip() can't do this: it only
        # trims matching chars from the ends, so a trailing comment after the
        # close (e.g. Redis's `#include <math.h> /* isnan() */` or
        # `#include "x.h" // note`) leaves the interior delimiter and the comment
        # intact → module_name `math.h> /* isnan() */` (BACK-417).
        module_name = self._extract_include_target(remainder) if self.spec.resolve_includes else None
        if module_name is None:
            # Non-include (import/using) or a malformed include: strip surrounding
            # quotes (angle brackets too for includes) as before.
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
        file_index: Optional[Dict[str, List[Path]]] = None,
    ) -> Optional[Path]:
        """Resolve an import to a real in-tree file (for the dependency graph).

        Dispatches by language shape:
          * ``resolve_includes`` (C/C++) → :meth:`_resolve_include` — quoted
            ``#include`` to a sibling/searched header; angle-bracket system
            includes return None.
          * ``source_extensions`` set (Java/PHP/Ruby/Swift/Kotlin, BACK-487/488)
            → :meth:`_resolve_module` — dotted type names and relative path
            literals to an in-tree source file.
          * neither → None (listing only; file-level graph not claimed).

        Returns a real, existing file every time or ``None`` — never a
        fabricated path. Self-reference filtering is the caller's job.

        ``file_index`` (BACK-491): an optional ``basename -> [full paths]`` map
        of every file under the (single) search root, prebuilt once by the
        caller (``ImportsAdapter._build_graph``) during its file-discovery walk.
        When supplied, multi-component resolution (include full-suffix match and
        dotted-name lookup alike) resolves by dict lookup instead of a full
        ``os.walk(root)`` per import — O(imports × tree) → O(tree + imports).
        The index must have been built from the same root passed in
        ``search_paths`` with the same ``SKIP_DIRECTORIES``/hidden-dir filtering
        (as ``_build_graph`` does), which makes the lookup byte-identical to the
        walk it replaces. Callers that pass no index (I002, call_graph, depends)
        fall back to the walk unchanged.
        """
        if self.spec.resolve_includes:
            return self._resolve_include(stmt, base_path, search_paths, file_index)
        if self.spec.source_extensions:
            return self._resolve_module(stmt, base_path, search_paths, file_index)
        return None

    def _resolve_include(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        file_index: Optional[Dict[str, List[Path]]] = None,
    ) -> Optional[Path]:
        """Resolve a quoted C/C++ ``#include`` to a real file (for the dep graph).

        System includes (``<stdio.h>``, ``is_relative=False``) return None —
        their file-level graph is not claimed. Quoted includes are looked up
        next to the including file first, then under each project search path.
        """
        if not stmt.is_relative:
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
            #
            # BACK-491: with a prebuilt index, iterate only the files sharing
            # this include's basename (in walk order) instead of re-walking the
            # whole tree. Because the index holds every file under `root` in the
            # same walk order and with the same skip-dir filter, the first
            # full-suffix match here is the same file the os.walk below would
            # return — just without the O(tree) scan per include.
            if file_index is not None:
                for candidate in file_index.get(target_parts[-1], ()):
                    if candidate.parts[-n:] == target_parts:
                        return candidate.resolve()
                continue
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

    # --- BACK-487/488: non-#include edge resolution ----------------------

    def _resolve_module(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Resolve a Java/PHP/Ruby/Swift/Kotlin import to an in-tree source file.

        Two shapes, distinguished structurally (never fabricating an edge):
          * **Qualified type name** joined by ``module_separator`` (Java
            ``com.pkg.Type``, PHP ``App\\Models\\User``, Kotlin
            ``com.pkg.Bar``) → :meth:`_resolve_dotted`.
          * **Path-style literal** (Ruby ``require_relative './x'``,
            ``load 'config.rb'``; PHP ``require 'lib/foo.php'``) → resolved
            relative to the including file, then project roots.
          * A single-token module (Swift ``import Foo``) is tried as a bare
            basename (``Foo.swift``) via the dotted path with one component.

        Wildcards (Java ``import a.b.*``, Scala ``import a.b._``) and selector
        imports (Scala ``import a.b.{C, D}``) name a package or multiple types
        rather than one file, and return None.
        """
        module = stmt.module_name
        if not module or module.endswith('*'):
            return None

        sep = self.spec.module_separator
        exts = self.spec.source_extensions
        prefix = self.spec.project_relative_prefix

        if prefix and module.startswith(prefix):
            # Project-root-relative virtual path (GDScript `res://...`) — never
            # file-relative, so resolve only against search_paths (the scan
            # root), skipping the base_path-relative attempt entirely.
            target = module[len(prefix):]
            return self._resolve_path_target(target, None, search_paths, exts)

        if sep and sep in module:
            parts = [p for p in module.split(sep) if p]
            # Scala selector `{C, D}` / wildcard `_` name multiple targets or a
            # whole package, not one file — skip rather than leak `{...}`/`_`
            # into a bogus path.
            if parts and (parts[-1] == '_' or '{' in parts[-1]):
                return None
            return self._resolve_dotted(parts, exts, search_paths, file_index)

        if self._looks_like_path(module, exts):
            return self._resolve_path_target(module, base_path, search_paths, exts)

        # Single-token module with no separator and no path markers: try it as a
        # bare basename (Swift `import Foo` → Foo.swift; Java default-package
        # `import Foo`). Only resolves when exactly one such file exists.
        if module.isidentifier():
            return self._resolve_dotted([module], exts, search_paths, file_index)

        return None

    @staticmethod
    def _looks_like_path(module: str, exts: FrozenSet[str]) -> bool:
        """True when a module string is a filesystem path, not a qualified name."""
        return (
            module.startswith('.')
            or '/' in module
            or any(module.endswith(e) for e in exts)
        )

    def _resolve_dotted(
        self,
        parts: List[str],
        exts: FrozenSet[str],
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Resolve a qualified type name (``[com, pkg, Type]``) to a source file.

        Matches the *longest* trailing path-suffix that uniquely identifies one
        in-tree file, so a PSR-4 vendor prefix (``App\\`` → ``src/``) or an
        unqualified default-package import still resolves without colliding
        across same-named types in different packages. Ambiguity at the most
        specific suffix → skip (never guess).
        """
        if not parts:
            return None
        for ext in exts:
            target_parts = parts[:-1] + [parts[-1] + ext]
            match = self._longest_unique_suffix(target_parts, search_paths, file_index)
            if match is not None:
                return match
        return None

    def _longest_unique_suffix(
        self,
        target_parts: List[str],
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Return the file whose path ends with the longest unique suffix of
        ``target_parts`` (last element carries the extension), or None.

        A bare-basename match (k=1) is accepted only when exactly one file in
        the tree bears that basename; otherwise at least one parent directory
        component must match to disambiguate. If even the most specific
        available suffix is ambiguous, resolution is skipped.
        """
        basename = target_parts[-1]
        candidates = self._index_lookup(basename, search_paths, file_index)
        if not candidates:
            return None
        n = len(target_parts)
        min_k = 1 if len(candidates) == 1 else 2
        for k in range(n, min_k - 1, -1):
            suffix = tuple(target_parts[-k:])
            matches = [c for c in candidates if c.parts[-k:] == suffix]
            if len(matches) == 1:
                return matches[0].resolve()
            if len(matches) > 1:
                # Already ambiguous at this (most-specific-available) suffix;
                # shorter suffixes only get more ambiguous. Skip, don't guess.
                return None
        return None

    def _resolve_path_target(
        self,
        module: str,
        base_path: Optional[Path],
        search_paths: Optional[List[Path]],
        exts: FrozenSet[str],
    ) -> Optional[Path]:
        """Resolve a path-style import literal to a real file.

        Tries the target verbatim and with each source extension appended
        (Ruby ``require_relative './helper'`` → ``helper.rb``), relative to the
        including file first, then each project root. ``base_path=None`` (GDScript
        ``res://``) skips the file-relative attempt and tries only project roots.
        """
        names = [module] + [module + e for e in exts if not module.endswith(e)]
        roots = ([base_path] if base_path is not None else []) + list(search_paths or [])
        for root in roots:
            for name in names:
                candidate = (root / name).resolve()
                if candidate.is_file():
                    return candidate
        return None

    @staticmethod
    def _index_lookup(
        basename: str,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> List[Path]:
        """All in-tree files bearing ``basename`` — via the prebuilt index when
        available (BACK-491), else a bounded walk of the search paths."""
        if file_index is not None:
            return list(file_index.get(basename, ()))
        found: List[Path] = []
        for root in search_paths or []:
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in SKIP_DIRECTORIES and not d.startswith('.')
                ]
                if basename in filenames:
                    found.append(Path(dirpath) / basename)
        return found


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
    module_separator='.',
    source_extensions=frozenset({'.java'}),
)

_CSHARP_SPEC = _ImportSpec(
    import_node_types=frozenset({'using_directive'}),
    keywords=frozenset({'using', 'global', 'static'}),
    alias_assignment=True,
    # `using X.Y` names a namespace (a directory of files), not one type, so a
    # dotted-name lookup resolves an edge only when a same-named `Y.cs` happens
    # to exist — otherwise skipped. Full C# fan-in needs a namespace-declaration
    # index, not filename matching (see module docstring).
    module_separator='.',
    source_extensions=frozenset({'.cs'}),
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
    module_separator='\\',  # `use App\Models\User`
    source_extensions=frozenset({'.php'}),
)

_RUBY_SPEC = _ImportSpec(
    import_node_types=frozenset(),  # no dedicated node — matched as calls
    keywords=frozenset({'require', 'require_relative', 'load'}),
    call_import_names=frozenset({'require', 'require_relative', 'load'}),
    # Ruby imports are always path-style literals — no qualified-name separator.
    source_extensions=frozenset({'.rb'}),
)

# BACK-488: Swift and Kotlin were absent from the table entirely — `imports://`,
# `architecture`, and every fan-in/circular-dep feature returned nothing for two
# of the most DD-relevant (mobile) languages. Node kinds verified against
# tree-sitter-language-pack real parses.
_SWIFT_SPEC = _ImportSpec(
    # `import Foundation` / `import struct Foo.Bar` — the whole path is the
    # import declaration; leading `struct`/`class`/`func`/etc. submodule kinds
    # are stripped as keywords.
    import_node_types=frozenset({'import_declaration'}),
    keywords=frozenset({
        'import', 'struct', 'class', 'enum', 'protocol', 'typealias',
        'func', 'let', 'var',
    }),
    # Swift `import Foo` names a module; resolves to Foo.swift only when the
    # module maps 1:1 to a single in-tree file (skipped otherwise).
    module_separator='.',
    source_extensions=frozenset({'.swift'}),
)

_KOTLIN_SPEC = _ImportSpec(
    import_node_types=frozenset({'import_header'}),
    keywords=frozenset({'import'}),
    module_separator='.',  # `import com.foo.Bar`
    source_extensions=frozenset({'.kt'}),
)

# BACK-514: Lua/Scala/Dart/Zig/GDScript were absent from the table entirely —
# `imports://`, `architecture`, `surface`, and `pack` silently built their
# picture from zero files of these five languages. Node kinds verified against
# real parses (2026-07-09, session apricot-tapestry-0709); see
# internal-docs/planning/BACK-514-import-coverage-implementation.md.
_SCALA_SPEC = _ImportSpec(
    # `import a.b.C` / `import a.b.{C, D}` / `import a.b._` are all one node
    # kind; selector/wildcard forms are recognised and skipped in
    # _resolve_module (they name multiple targets, not one file).
    import_node_types=frozenset({'import_declaration'}),
    keywords=frozenset({'import'}),
    module_separator='.',
    source_extensions=frozenset({'.scala'}),
)

_DART_SPEC = _ImportSpec(
    # `export`/`part` directives are separate node kinds (library_export,
    # part_directive) and are intentionally not matched here — out of scope
    # for v1 (imports only).
    import_node_types=frozenset({'import_specification'}),
    keywords=frozenset({'import'}),
    # Dart imports are path-style literals (relative `./x.dart` or a
    # `package:x/y.dart` reference) — no qualified-name separator. A
    # `package:` reference resolves only if it happens to name a real in-tree
    # path; otherwise it is honestly skipped (never fabricated).
    source_extensions=frozenset({'.dart'}),
)

_GDSCRIPT_SPEC = _ImportSpec(
    # Two independent import shapes in one spec: `extends "res://base.gd"`
    # (dedicated node) and `preload(...)`/`load(...)` (call-style).
    import_node_types=frozenset({'extends_statement'}),
    keywords=frozenset({'extends'}),
    call_import_names=frozenset({'preload', 'load'}),
    source_extensions=frozenset({'.gd'}),
    # `res://` is Godot's project-root-relative virtual filesystem, not
    # file-relative — resolved only against search_paths (see _resolve_module).
    project_relative_prefix='res://',
)

_LUA_SPEC = _ImportSpec(
    import_node_types=frozenset(),  # no dedicated node — matched as calls
    keywords=frozenset({'require'}),
    call_import_names=frozenset({'require'}),
    call_node_type='function_call',  # Lua's call node kind, unlike Ruby's `call`
    # `require("a.b")` uses `.` as a path separator by Lua convention →
    # a/b.lua, resolved the same way Java's dotted package names are.
    module_separator='.',
    source_extensions=frozenset({'.lua'}),
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


@register_extractor
class SwiftImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.swift'}
    language_name = 'Swift'
    spec = _SWIFT_SPEC


@register_extractor
class KotlinImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.kt', '.kts'}
    language_name = 'Kotlin'
    spec = _KOTLIN_SPEC


@register_extractor
class ScalaImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.scala'}
    language_name = 'Scala'
    spec = _SCALA_SPEC


@register_extractor
class DartImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.dart'}
    language_name = 'Dart'
    spec = _DART_SPEC


@register_extractor
class GDScriptImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.gd'}
    language_name = 'GDScript'
    spec = _GDSCRIPT_SPEC


@register_extractor
class LuaImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.lua'}
    language_name = 'Lua'
    spec = _LUA_SPEC


__all__ = [
    '_ImportSpec',
    '_GenericTreeSitterImportExtractor',
    'CImportExtractor',
    'CppImportExtractor',
    'JavaImportExtractor',
    'CSharpImportExtractor',
    'PhpImportExtractor',
    'RubyImportExtractor',
    'SwiftImportExtractor',
    'KotlinImportExtractor',
    'ScalaImportExtractor',
    'DartImportExtractor',
    'GDScriptImportExtractor',
    'LuaImportExtractor',
]
