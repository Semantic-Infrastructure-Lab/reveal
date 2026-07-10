"""depends:// adapter — Inverse module dependency graph.

Answer "what depends on this module?" by inverting the import graph.

Usage:
    reveal depends://src/utils.py          # Who imports utils.py?
    reveal depends://src/models/           # Who imports anything in models/?
    reveal 'depends://src?top=20'          # Most-imported files
    reveal 'depends://src?format=dot'      # GraphViz output
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import safe_json_dumps
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages
from ..defaults import SKIP_DIRECTORIES
from ..utils.query import parse_query_params
from ..utils.path_utils import search_parents, search_parents_within_ceiling

# BACK-498: find_project_root()'s built-in default markers (pyproject.toml,
# setup.py/.cfg, .git, Cargo.toml, package.json, go.mod) are Python/JS/Rust/Go-
# centric — they miss the root marker every package/namespace-resolved language
# in this adapter's scope actually uses, so for Java/Kotlin/C#/Swift/PHP repos
# without a discoverable .git it always fell through to the too-narrow parent-
# dir fallback below. Passed explicitly (not merged into path_utils' shared
# default) so this widening is scoped to depends://'s own root search and
# doesn't change behavior for I002/D005/B005's separate, private
# _find_project_root copies. 'settings.gradle(.kts)' and '*.sln' are true
# root-only markers (Gradle forbids nested settings files; a solution file
# sits above its .csproj members) so they can't cause the "found a marker
# several modules too deep" problem 'pom.xml'/'composer.json' risk in a
# multi-module tree — those two are still net improvements over the bare
# parent-dir fallback even when they resolve to a submodule root rather than
# the monorepo root.
#
# BACK-515: this list MUST cover the root marker of every language depends://
# builds an import graph for — a missing marker isn't a cosmetic gap, it's a
# hang. When no marker is found, search_parents climbs until it hits ANY
# ancestor marker (commonly a `.git` far above the real project), and
# _build_graph then tries to parse every file under it. BACK-514 added
# import-graph coverage for Lua/Scala/Dart/Zig/GDScript but only Lua's marker
# reached this list initially; Scala and Dart then reproduced the identical
# "hang" (a full monorepo scan) — see RESOLVED_LEDGER. The five markers below
# close that. Each is one-per-package and can nest in a multi-module tree, so
# like 'pom.xml'/'composer.json' they may resolve to a submodule root rather
# than the monorepo root — a bounded, correct-enough scope, and vastly better
# than climbing to an unrelated ancestor repo.
# BACK-525: split into two tiers — a package/build marker is *positive
# project-unit evidence*; a VCS root (`.git`) is checked only if no package
# marker exists anywhere in the climb. Conflating them (the old flat
# `_PROJECT_ROOT_MARKERS`) is what let a distant ancestor `.git` get promoted
# to a scan root when nothing closer existed — the marker was "found" but was
# really just a climb-ceiling signal, not a project unit. See
# internal-docs/design/SCAN_ROOT_RESOLUTION_2026-07-09.md.
_PACKAGE_ROOT_MARKERS = [
    'pyproject.toml', 'setup.py', 'setup.cfg', 'Cargo.toml',
    'package.json', 'go.mod',
    'settings.gradle', 'settings.gradle.kts',  # Java/Kotlin (Gradle)
    'pom.xml',  # Java (Maven)
    'Package.swift',  # Swift (SPM)
    'composer.json',  # PHP
    'build.sbt', 'build.sc',  # Scala (sbt / Mill)  — BACK-515
    'pubspec.yaml',  # Dart (pub)                    — BACK-515
    'build.zig',  # Zig                              — BACK-515
    'project.godot',  # GDScript (Godot)             — BACK-515
]

_VCS_ROOT_MARKERS = ['.git']

# Back-compat union — every marker (package or VCS) `_has_project_marker`
# recognized before BACK-525's tiering split. Still used where "is there any
# marker at all in this one directory" is the actual question (tests).
_PROJECT_ROOT_MARKERS = _PACKAGE_ROOT_MARKERS + _VCS_ROOT_MARKERS


def _has_package_marker(directory: Path) -> bool:
    """True if *directory* holds positive project-unit evidence (BACK-525
    tier 1) — a package/build marker, never a bare VCS root.

    Extends the literal-filename check with two repo-specific-name globs:
    `*.sln` (C# solution files) and `*.rockspec` (Lua/LuaRocks package
    specs) — neither can be a fixed literal in `_PACKAGE_ROOT_MARKERS`
    because both carry a project-specific name.
    """
    if any((directory / marker).exists() for marker in _PACKAGE_ROOT_MARKERS):
        return True
    return any(directory.glob('*.sln')) or any(directory.glob('*.rockspec'))


def _has_vcs_marker(directory: Path) -> bool:
    """True if *directory* is a VCS root (BACK-525 tier 2) — checked only
    when no package marker exists anywhere in the climb."""
    return any((directory / marker).exists() for marker in _VCS_ROOT_MARKERS)


def _has_project_marker(directory: Path) -> bool:
    """True if *directory* holds a depends:// project-root marker (package
    or VCS, union of both tiers). See the BACK-515 note above for why a
    missing marker is a hang, not a cosmetic gap; see BACK-525 for why the
    tiers matter for *which* marker gets promoted to a scan root.
    """
    return _has_package_marker(directory) or _has_vcs_marker(directory)


def _resolve_project_root(target_path: Path) -> Optional[Path]:
    """Tiered nearest-marker resolution (BACK-525 layers 1+2): a near
    package/build marker beats a distant VCS root, and the climb is bounded
    by a hard ceiling it can never promote to a root. Returns ``None`` if
    neither tier finds anything before the ceiling — the caller falls back
    to the inferred-project scope (layer 3).
    """
    package_root = search_parents_within_ceiling(target_path, _has_package_marker)
    if package_root is not None:
        return package_root
    return search_parents_within_ceiling(target_path, _has_vcs_marker)

_SCHEMA_QUERY_PARAMS = {
    'top': {
        'type': 'integer',
        'description': 'Limit to the N most-imported files',
        'examples': ["depends://src?top=10"],
    },
    'format': {
        'type': 'string',
        'description': 'Output format: text (default) or dot (GraphViz)',
        'examples': ["depends://src?format=dot"],
    },
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'module_dependents',
        'description': 'List of files that import the target module(s)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'module_dependents'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'target': {'type': 'string'},
                'dependents': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'line': {'type': 'integer'},
                            'module': {'type': 'string'},
                            'names': {'type': 'array', 'items': {'type': 'string'}},
                            'type': {'type': 'string'},
                            'is_relative': {'type': 'boolean'},
                            'alias': {'type': 'string'},
                        },
                    },
                },
                'count': {'type': 'integer'},
            },
        },
    },
    {
        'type': 'dependency_summary',
        'description': 'Most-imported modules in a directory',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'dependency_summary'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'modules': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'module': {'type': 'string'},
                            'dependent_count': {'type': 'integer'},
                            'dependents': {'type': 'array', 'items': {'type': 'string'}},
                        },
                    },
                },
            },
        },
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'depends://src/utils.py',
        'description': 'Show all files that import utils.py',
        'output_type': 'module_dependents',
    },
    {
        'uri': 'depends://src/models/',
        'description': 'Show everything that imports any module in models/',
        'output_type': 'dependency_summary',
    },
    {
        'uri': "depends://src?top=10",
        'description': 'The 10 most-imported modules in src (high coupling candidates)',
        'output_type': 'dependency_summary',
    },
    {
        'uri': "depends://src?format=dot",
        'description': 'Full reverse dependency graph in GraphViz DOT format',
        'output_type': 'dependency_summary',
    },
]

_SCHEMA_NOTES = [
    'Inverts the import graph built by imports:// — same language support, same resolution',
    'Dynamic imports (importlib.import_module, __import__) are not tracked',
    'TYPE_CHECKING-only imports are excluded from edges (intentional)',
    'Results are conservative: false negatives possible, never false positives',
    'Use ?top=N on a directory to find high-coupling modules (many dependents = high impact if changed)',
    'Use depends://file.py to do impact analysis before refactoring a module',
]


class DependsRenderer:
    """Renderer for depends:// results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text', verbose: bool = False, resource: str = '.') -> None:
        if format == 'json':
            print(safe_json_dumps(result))
            return

        result_type = result.get('type')
        if result_type == 'module_dependents':
            DependsRenderer._render_dependents(result, verbose)
        elif result_type == 'dependency_summary':
            fmt = result.get('_format', 'text')
            if fmt == 'dot':
                DependsRenderer._render_dot(result)
            else:
                DependsRenderer._render_summary(result, verbose, resource)
        else:
            print(safe_json_dumps(result))

    @staticmethod
    def _render_dependents(result: dict, verbose: bool) -> None:
        target = result.get('target', 'unknown')
        dependents = result.get('dependents', [])
        count = result.get('count', 0)

        print(f"\n{'='*60}")
        print(f"Dependents of: {target}")
        print(f"{'='*60}\n")

        warning = result.get('warning')
        if warning:
            print(f"{warning}\n")

        if not dependents:
            print("  No dependents found (nothing imports this module)")
            print()
            print("ℹ Import-graph analysis — dynamic imports not followed.")
            return

        print(f"  {count} file(s) import this module:\n")
        for dep in dependents:
            file_path = dep.get('file', '')
            line = dep.get('line', 0)
            names = dep.get('names', [])
            import_type = dep.get('type', '')
            alias = dep.get('alias')

            if import_type == 'star_import':
                what = '*'
            elif names:
                what = ', '.join(names[:5])
                if len(names) > 5:
                    what += f', … (+{len(names) - 5} more)'
            else:
                what = dep.get('module', '')

            alias_str = f' as {alias}' if alias else ''
            print(f"  {file_path}:{line}  ← {what}{alias_str}")

        print()
        if not verbose:
            print(f"  Tip: reveal depends://{target} --verbose  for full import detail")
            print()
        print("ℹ Import-graph analysis — dynamic imports not followed.")
        print()

    @staticmethod
    def _render_summary(result: dict, verbose: bool, resource: str) -> None:
        modules = result.get('modules', [])
        source = result.get('source', resource)

        print(f"\n{'='*60}")
        print(f"Reverse Dependency Summary: {source}")
        print(f"{'='*60}\n")

        warning = result.get('warning')
        if warning:
            print(f"{warning}\n")

        if not modules:
            print("  No internal imports found.")
            print()
            print("ℹ Import-graph analysis — dynamic imports not followed.")
            return

        total = sum(m['dependent_count'] for m in modules)
        print(f"  {len(modules)} module(s) imported internally ({total} total import edges)\n")

        for m in modules:
            count = m['dependent_count']
            mod = m['module']
            bar = '█' * min(count, 20)
            print(f"  {count:3d}  {bar}  {mod}")
            if verbose:
                for dep in m.get('dependents', []):
                    print(f"         ← {dep}")

        print()
        print(f"  Tip: reveal depends://<module>  for full importer list")
        print()
        print("ℹ Import-graph analysis — dynamic imports not followed.")
        print()

    @staticmethod
    def _render_dot(result: dict) -> None:
        modules = result.get('modules', [])
        print('digraph depends {')
        print('  rankdir=LR;')
        print('  node [shape=box fontname="monospace" fontsize=10];')
        for m in modules:
            target = m['module'].replace('"', '\\"')
            for dep in m.get('dependents', []):
                src = dep.replace('"', '\\"')
                print(f'  "{src}" -> "{target}";')
        print('}')

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        if format == 'json':
            print(safe_json_dumps(result))
            return
        DependsRenderer._render_dependents(result, verbose=True)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error: {error}", file=sys.stderr)


@register_adapter('depends')
@register_renderer(DependsRenderer)
class DependsAdapter(ResourceAdapter):
    """Inverse module dependency graph — who imports this module?

    Builds the same import graph as imports:// but queries it in reverse:
    given a target module (or directory), returns the set of files that
    depend on it.
    """

    # BACK-524: bound the tree-sitter-parsed file set so a scan_root that
    # resolves to a genuinely huge (but marker-legit) ancestor repo degrades
    # to a warned, partial result instead of an unbounded parse — the residual
    # class BACK-515's marker fix couldn't close (a file with no marker above
    # it at all, or a future depends://-supported language whose marker isn't
    # in _PROJECT_ROOT_MARKERS yet). Counts only extractor-supported files
    # (what's actually expensive to parse), not every file os.walk visits.
    _SCAN_FILE_CAP = 5000

    def __init__(self, path: str = '.', query: Optional[str] = None):
        """Initialize depends adapter.

        Args:
            path: File or directory to find dependents for
            query: Query string (e.g., 'top=10', 'format=dot')
        """
        self._graph: Optional[ImportGraph] = None
        self._symbols_by_file: Dict[Path, set] = {}
        self._target_path: Optional[Path] = Path(path).resolve() if path else None
        self._query_params = parse_query_params(query or '')
        self._warn_unknown_query_params(self._query_params)  # BACK-507
        self._scan_root: Optional[Path] = None
        self._scan_capped = False
        self._root_inferred = False

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Build import graph and return reverse-dependency view.

        Returns:
            - module_dependents if target is a specific file
            - dependency_summary if target is a directory
        """
        target_path = self._target_path or Path('.').resolve()

        if not target_path.exists():
            return {'error': f"Path not found: {target_path}"}

        # For a specific file target: scan from project root so ALL importers
        # (not just siblings) are discovered.
        # For a directory target: same — scan from project root so files outside
        # the directory that import into it are visible.
        #
        # BACK-498: when no project marker exists above a *file* target, falling
        # back straight to the file's own parent directory is too narrow for
        # package/namespace-resolved languages (Java, Kotlin, Swift, PHP) — a
        # dependent commonly lives in a sibling package directory
        # (src/main/java/com/example/{util,app}/...), not the same folder. Widen
        # to the nearest conventional source root ('src', the Maven/Gradle/iOS/
        # Composer convention that all four affected languages share) when one
        # exists above the file; only fall back to the bare parent dir if even
        # that isn't found.
        # BACK-525 layers 1+2: tiered nearest-marker climb, bounded by a hard
        # ceiling it can never itself become the answer to.
        project_root = _resolve_project_root(target_path)
        if project_root is None:
            # BACK-525 layer 3: inferred-project fallback (tsserver's model)
            # — no marker found before the ceiling, so don't scan the
            # ceiling itself. Scope to the target's own subtree and say so,
            # rather than silently pulling in whatever unrelated sibling
            # happens to share that ceiling (the `~/src/{p1,p2}` case).
            self._root_inferred = True
            if target_path.is_dir():
                project_root = target_path
            else:
                src_root = search_parents(target_path, lambda p: p.name == 'src')
                project_root = src_root if src_root else target_path.parent
        self._target_path = target_path
        # BACK-525 layer 4: for a single-file target, only files in its own
        # extractor's `extensions` family (e.g. C's .c+.h) can ever satisfy
        # resolve_import's extension-qualified lookup (verified read-only,
        # gate G1) — parsing every other supported language's files under
        # scan_root just to build the dependency graph is pure waste. A
        # directory target may span languages, so it stays unscoped.
        scan_extensions = None
        if target_path.is_file():
            target_extractor = get_extractor(target_path)
            if target_extractor is not None:
                scan_extensions = frozenset(target_extractor.extensions)
        self._build_graph(project_root, scan_extensions=scan_extensions)

        fmt = self._query_params.get('format', 'text')
        if not isinstance(fmt, str):
            fmt = 'text'
        top_n_raw = self._query_params.get('top')
        top_n = int(top_n_raw) if top_n_raw else None

        if target_path.is_file():
            return self._format_file_dependents(target_path)
        else:
            return self._format_directory_summary(target_path, top_n=top_n, fmt=fmt)

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get dependents for a specific module by name.

        Args:
            element_name: File name (e.g., 'utils.py')
        """
        if not self._graph:
            return None

        for file_path in self._graph.reverse_deps:
            if file_path.name == element_name:
                return self._format_file_dependents(file_path)

        return None

    def get_metadata(self) -> Dict[str, Any]:
        if not self._graph:
            return {'status': 'not_analyzed'}
        return {
            'total_files_scanned': self._graph.get_file_count(),
            'total_import_edges': sum(len(v) for v in self._graph.reverse_deps.values()),
            'analyzer': 'depends',
            'scan_capped': self._scan_capped,
            'root_inferred': self._root_inferred,
        }

    # ── Graph building (mirrors ImportsAdapter._build_graph) ──────────────

    def _build_graph(self, scan_root: Path, scan_extensions: Optional[frozenset] = None) -> None:
        """Build import graph from scan_root.

        ``scan_extensions`` (BACK-525 layer 4): when given, restricts the
        *parse corpus* (``files`` — what actually gets tree-sitter'd for
        import statements) to this extension set, the target's own
        extractor family (e.g. C's ``.c``/``.h``). This is where the cost
        lives, so it's where the win is; ``file_index`` (the resolution
        basename map) stays extension-agnostic regardless, since it needs
        to hold non-source-extension include targets too (BACK-491:
        ``.inc``/``.tcc``). A basename lookup only ever matches a file whose
        name is extension-qualified to the *importing* language (verified
        read-only, gate G1), so a file outside the target's family could
        never satisfy a resolution anyway — narrowing the parse corpus to
        it is correct-by-construction, not a heuristic, and dissolves the
        file-count cap's non-determinism for single-language targets
        (``None`` — directory targets, which may span languages — stays
        unscoped across every supported extension, the pre-BACK-525 shape).
        """
        supported_exts = scan_extensions if scan_extensions is not None else frozenset(get_all_extensions())
        self._scan_root = scan_root
        self._scan_capped = False

        # BACK-498: discover files the same way ImportsAdapter._build_graph does —
        # os.walk honoring SKIP_DIRECTORIES/hidden dirs (not a raw rglob, which
        # both scans build artifacts/vendor dirs it shouldn't and, on a repo where
        # scan_root ends up far above the real project, times out) — and build a
        # basename -> [full paths] index alongside it. Package/namespace-resolved
        # languages (Java, Kotlin, C#, PHP, Swift) need that index to resolve a
        # dotted/qualified import to a file without their own tree walk; without
        # it `resolve_import` silently fails for every such import and depends://
        # reports "No dependents found" even though imports://?rank=fan-in sees
        # the same edge (BACK-491 built this index for imports:// only).
        files: List[Path] = []
        file_index: Dict[str, List[Path]] = {}
        if scan_root.is_file():
            if scan_root.suffix in supported_exts:
                files.append(scan_root)
        else:
            for root, dirs, filenames in os.walk(str(scan_root)):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRECTORIES and not d.startswith('.')]
                capped = False
                for fname in filenames:
                    fp = Path(root) / fname
                    # file_index stays extension-agnostic (BACK-491: quoted
                    # C/C++ #include targets can be non-source extensions
                    # like .inc/.tcc) even when scan_extensions narrows what
                    # actually gets *parsed* below — only the parse corpus
                    # is the expensive part language-scoping needs to cut.
                    file_index.setdefault(fname, []).append(fp)
                    if fp.suffix not in supported_exts:
                        continue
                    if len(files) >= self._SCAN_FILE_CAP:
                        capped = True
                        break
                    files.append(fp)
                if capped:
                    self._scan_capped = True
                    break

        all_imports: List[ImportStatement] = []
        for file_path in files:
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            imports = extractor.extract_imports(file_path)
            all_imports.extend(imports)

        self._graph = ImportGraph.from_imports(all_imports)

        # Resolve to build dependency (and reverse_deps) edges
        for file_path, imports in self._graph.files.items():
            extractor = get_extractor(file_path)
            if not extractor:
                continue

            base_path = file_path.parent
            extra_paths = [scan_root] if scan_root.is_dir() and scan_root != base_path else []
            # Mirrors ImportsAdapter._build_graph's gating (BACK-491): only
            # generic (spec-based) extractors accept file_index.
            uses_file_index = getattr(extractor, 'spec', None) is not None
            for stmt in imports:
                if stmt.is_type_checking:
                    continue
                if uses_file_index:
                    resolved = extractor.resolve_import(
                        stmt, base_path, search_paths=extra_paths, file_index=file_index)
                else:
                    resolved = extractor.resolve_import(stmt, base_path, search_paths=extra_paths)
                if resolved and resolved != file_path:
                    self._graph.add_dependency(file_path, resolved)
                    self._graph.resolved_paths[stmt.module_name] = resolved

    def _build_meta(self) -> Dict[str, Any]:
        known_limits = [
            'dynamic imports (importlib, __import__) not followed',
            'conditional imports may not reflect runtime state',
            'TYPE_CHECKING-only imports are excluded',
        ]
        if self._scan_capped:
            known_limits.append(
                f'scan capped at {self._SCAN_FILE_CAP:,} files — BACK-524, results may be partial')
        if self._root_inferred:
            known_limits.append(
                "no project marker found above the target before the scan-root ceiling — "
                "BACK-525, scope inferred from the target's own directory")
        return {
            'analysis_kind': 'import-graph',
            'confidence': 'high',
            'known_limits': known_limits,
        }

    def _scan_cap_warning(self) -> str:
        """BACK-524: one-line disclosure when _build_graph stopped early.

        Mirrors imports.py's coverage_warning_line — a partial graph must say
        so, not present itself as complete (same principle as BACK-518 part 2).
        """
        if not self._scan_capped:
            return ''
        root = self._scan_root
        return (
            f"⚠ Scan capped at {self._SCAN_FILE_CAP:,} files under {root} — "
            "results may be incomplete. Scope depends:// to a narrower path "
            "for a complete scan."
        )

    def _root_inferred_warning(self) -> str:
        """BACK-525 layer 3: one-line disclosure when no project marker was
        found above the target before the scan-root ceiling, so the scan was
        scoped to the target's own directory instead of climbing further."""
        if not self._root_inferred:
            return ''
        root = self._scan_root
        return (
            f"⚠ Couldn't determine this file's project boundary — scanning only "
            f"{root}. Pass an explicit root or cd into the project for full coverage."
        )

    def _warnings(self) -> str:
        """Join every active disclosure (scan cap, inferred root) into one
        warning string, in priority order."""
        parts = [w for w in (self._scan_cap_warning(), self._root_inferred_warning()) if w]
        return '\n'.join(parts)

    # ── Formatters ─────────────────────────────────────────────────────────

    def _format_file_dependents(self, target: Path) -> Dict[str, Any]:
        """Format all files that import `target`."""
        if not self._graph:
            return {'error': 'Graph not built'}

        importer_files: Set[Path] = self._graph.reverse_deps.get(target, set())

        # Gather the actual ImportStatements pointing to target
        dependents = []
        for importer in sorted(importer_files):
            stmts = self._graph.files.get(importer, [])
            for stmt in stmts:
                resolved = self._graph.resolved_paths.get(stmt.module_name)
                if resolved == target:
                    dependents.append(_format_import_stmt(stmt))

        # If we couldn't match via resolved_paths, fall back to raw importer list
        if not dependents and importer_files:
            for importer in sorted(importer_files):
                dependents.append({'file': str(importer), 'line': 0, 'module': '', 'names': [], 'type': 'unknown', 'is_relative': False, 'alias': None})

        result = {
            'contract_version': '1.1',
            'type': 'module_dependents',
            'source': str(self._target_path),
            'source_type': 'file',
            'target': str(target),
            'dependents': dependents,
            'count': len(dependents),
            'metadata': self.get_metadata(),
            '_meta': self._build_meta(),
        }
        if self._scan_capped or self._root_inferred:
            result['warning'] = self._warnings()
        return result

    def _format_directory_summary(self, directory: Path, top_n: Optional[int], fmt: str) -> Dict[str, Any]:
        """Format most-imported modules in directory, sorted by dependent count."""
        if not self._graph:
            return {'error': 'Graph not built'}

        # Only include modules that live inside the directory
        modules = []
        for target, importers in self._graph.reverse_deps.items():
            if not _path_is_under(target, directory):
                continue
            modules.append({
                'module': str(target),
                'dependent_count': len(importers),
                'dependents': sorted(str(p) for p in importers),
            })

        modules.sort(key=lambda m: m['dependent_count'], reverse=True)

        if top_n:
            modules = modules[:top_n]

        result = {
            'contract_version': '1.1',
            'type': 'dependency_summary',
            'source': str(self._target_path),
            'source_type': 'directory',
            '_format': fmt,
            'modules': modules,
            'metadata': self.get_metadata(),
            '_meta': self._build_meta(),
        }
        if self._scan_capped or self._root_inferred:
            result['warning'] = self._warnings()
        return result

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'depends',
            'description': 'Inverse module dependency graph — who imports this module?',
            'uri_syntax': 'depends://<path>[?query]',
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': {},
            'cli_flags': ['--verbose'],
            'supports_batch': False,
            'supports_advanced': False,
            'supported_languages': get_supported_languages(),
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'depends',
            'description': 'Inverse module dependency graph — who imports this module?',
            'syntax': 'depends://<path>[?<query>]',
            'examples': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
            'supported_languages': get_supported_languages(),
        }


# ── Helpers ────────────────────────────────────────────────────────────────

def _format_import_stmt(stmt: ImportStatement) -> Dict[str, Any]:
    return {
        'file': str(stmt.file_path),
        'line': stmt.line_number,
        'module': stmt.module_name,
        'names': stmt.imported_names,
        'type': stmt.import_type,
        'is_relative': stmt.is_relative,
        'alias': stmt.alias,
    }


def _path_is_under(path: Path, directory: Path) -> bool:
    """True if path is inside directory (or is directory itself)."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False
