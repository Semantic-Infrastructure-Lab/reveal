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
from typing import Dict, Any, List, Optional, Set, Tuple

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
            if result.get('undercount_possible'):
                # BACK-547: the caveat (⚠) already printed above; do not assert
                # the confident "nothing imports this module" that contradicts it.
                print("  No dependents resolved — but see the ⚠ above: this may be incomplete.")
            else:
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
            if result.get('undercount_possible'):
                print("  No internal imports resolved — but see the ⚠ above: this may be incomplete.")
            else:
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
        # BACK-542: (importer, target) → the exact ImportStatement that produced
        # the edge, so display resolves the right import line even when one
        # statement resolves to several targets (`from pkg import a, b`).
        self._edge_stmts: Dict[tuple, 'ImportStatement'] = {}
        self._target_path: Optional[Path] = Path(path).resolve() if path else None
        self._query_params = parse_query_params(query or '')
        self._warn_unknown_query_params(self._query_params)  # BACK-507
        self._scan_root: Optional[Path] = None
        self._scan_capped = False
        self._root_inferred = False
        # BACK-547 honest-decline: import statements that were extracted and
        # point intra-project (per the extractor's is_intra_project_import) but
        # produced no graph edge — the false-negative risk a blast-radius
        # negative must disclose rather than assert a confident "nothing here".
        self._unresolved_intra = 0
        self._unresolved_examples: List[tuple] = []

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
        self._unresolved_intra = 0
        self._unresolved_examples = []

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
        # BACK-547/544/549: the set of packages/namespaces the tree declares,
        # for honest-decline classification of package-declaring languages
        # (C#, and since this session, Java/Kotlin/PHP) — an unresolved
        # dotted import is intra-project iff the project declares a matching
        # package/namespace. Only files whose extractor supports it
        # contribute (no-op scan otherwise); Swift has no such declaration to
        # scan and stays on the conservative None verdict.
        project_namespaces: Set[str] = set()
        # BACK-547 Kotlin measurement loop: (package, symbol) -> [declaring
        # files], the top-level free-function/property index that
        # resolve_member_targets looks up. `import a.b.foo` for a top-level
        # `fun foo`/`val foo` has no enclosing type anywhere in the import
        # string, so neither the direct dotted match nor BACK-551's
        # enclosing-class peel can find the declaring file — only a
        # content-scanned index over each package's files can. Built the same
        # way ImportsAdapter._build_namespace_index builds its namespace
        # index (every scanned file, not just ones with their own imports),
        # gated per-language via `spec.member_symbol_fallback` so this is a
        # no-op scan for trees with no such language present.
        member_index: Dict[Tuple[str, str], List[Path]] = {}
        for file_path in files:
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            all_imports.extend(extractor.extract_imports(file_path))
            spec = getattr(extractor, 'spec', None)
            if getattr(spec, 'resolve_namespaces', False) or getattr(spec, 'package_node_types', None):
                declared = extractor.extract_namespaces(file_path)
                project_namespaces.update(declared)
                if getattr(spec, 'member_symbol_fallback', False) and declared:
                    for symbol in extractor.extract_top_level_members(file_path):
                        for ns in declared:
                            member_index.setdefault((ns, symbol), []).append(file_path)

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
                    # Generic extractors' resolve_import needs the file_index
                    # kwarg the base resolve_import_targets can't pass, and
                    # don't have the `from pkg import submodule` idiom — single
                    # resolution is correct for them.
                    resolved = extractor.resolve_import(
                        stmt, base_path, search_paths=extra_paths, file_index=file_index)
                    targets = [resolved] if resolved else []
                else:
                    # BACK-542: one statement can pull in several files
                    # (`from pkg import a, b` where a/b are submodules), so
                    # resolve to the full target set, not just the primary.
                    targets = extractor.resolve_import_targets(
                        stmt, base_path, search_paths=extra_paths)
                added = False
                for resolved in targets:
                    if resolved and resolved != file_path:
                        self._graph.add_dependency(file_path, resolved)
                        self._graph.resolved_paths[stmt.module_name] = resolved
                        self._edge_stmts[(file_path, resolved)] = stmt
                        added = True
                if not added and member_index and getattr(
                        getattr(extractor, 'spec', None), 'member_symbol_fallback', False):
                    # BACK-547 Kotlin measurement loop: `import a.b.foo` for a
                    # top-level fun/val/var — the direct dotted match above
                    # looked for `foo.kt` and failed, and BACK-551's
                    # enclosing-class peel can't help either (there is no
                    # enclosing type in the import path to peel down to).
                    # Fall back to the content-scanned member index.
                    for resolved in extractor.resolve_member_targets(stmt, member_index):
                        if resolved != file_path:
                            self._graph.add_dependency(file_path, resolved)
                            self._edge_stmts[(file_path, resolved)] = stmt
                            added = True
                if not added:
                    # BACK-547 honest-decline: an extracted import that produced
                    # no edge is only a false-negative risk if it points
                    # intra-project. External (stdlib/dep) imports correctly have
                    # no in-tree edge; None means the extractor can't tell, and
                    # we conservatively don't count it (never cry wolf).
                    verdict = extractor.is_intra_project_import(
                        stmt, base_path, search_paths=extra_paths,
                        project_namespaces=project_namespaces)
                    if verdict is True:
                        self._unresolved_intra += 1
                        if len(self._unresolved_examples) < 5:
                            self._unresolved_examples.append((file_path, stmt))

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
        if self._unresolved_intra > 0:
            known_limits.append(
                f'{self._unresolved_intra} intra-project import(s) did not resolve to a file — '
                'BACK-547, dependents may be undercounted (a negative is a lower bound)')
        return {
            'analysis_kind': 'import-graph',
            # BACK-547: a graph with unresolved intra-project imports is not a
            # high-confidence source for a blast-radius negative.
            'confidence': 'reduced' if self._unresolved_intra > 0 else 'high',
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

    def _honest_decline_warning(self) -> str:
        """BACK-547 honest-decline: one-line disclosure when the scan contained
        intra-project imports that did not resolve to a file edge, so a
        blast-radius negative here is a lower bound, not a proof of "nothing
        imports this". Only intra-project misses count — external (stdlib/dep)
        imports are correctly edge-less and never trigger this."""
        n = self._unresolved_intra
        if n <= 0:
            return ''
        eg = ''
        if self._unresolved_examples:
            _importer, stmt = self._unresolved_examples[0]
            eg = f" (e.g. '{stmt.module_name}')"
        return (
            f"⚠ {n} intra-project import{'s' if n != 1 else ''} in this scan did not "
            f"resolve to a file{eg} — dependents may be undercounted, or those targets "
            "lie outside the scanned scope. Treat blast-radius negatives here as a lower bound."
        )

    def _warnings(self, include_honest_decline: bool = False) -> str:
        """Join active disclosures (scan cap, inferred root, and — only when the
        result is empty — honest-decline) into one warning string, in priority
        order. The honest-decline ⚠ is gated to the empty/negative case (the
        DD-killer BACK-542 signature): on a *positive* result the same
        intra-project-miss count is disclosed via _meta.known_limits instead, so
        a corpus with a few unresolved imports doesn't append a caveat to every
        confident, non-empty answer (that would be the cry-wolf failure honest-
        decline is meant to prevent)."""
        parts = [self._scan_cap_warning(), self._root_inferred_warning()]
        if include_honest_decline:
            parts.append(self._honest_decline_warning())
        return '\n'.join(w for w in parts if w)

    # ── Formatters ─────────────────────────────────────────────────────────

    def _format_file_dependents(self, target: Path) -> Dict[str, Any]:
        """Format all files that import `target`."""
        if not self._graph:
            return {'error': 'Graph not built'}

        importer_files: Set[Path] = set(self._graph.reverse_deps.get(target, set()))

        # BACK-553: package-granularity languages (Go) resolve an import to
        # the package DIRECTORY, not the individual file — `import "pkg/x"`
        # pulls in every .go file under x's directory as one package
        # (go.py's resolve_import returns the directory by design), so
        # add_dependency/reverse_deps is keyed by that directory, never by
        # any single file inside it. Without this fallback, EVERY file-level
        # depends://<file>.go query hits the exact-file lookup above, finds
        # nothing (the key that exists is the directory, not this file), and
        # confidently reports zero dependents even when the package has
        # hundreds of real importers — the archetypal BACK-542/BACK-547
        # silent false negative, and it fires on 100% of Go file targets.
        # Falling back to the containing directory is safe for every
        # language: reverse_deps keys are never arbitrary directories, only
        # values some extractor's resolve_import actually returned, so a hit
        # here only ever means "an import resolved to this exact directory
        # as its package."
        dir_target = target.parent
        dir_importers = self._graph.reverse_deps.get(dir_target)
        used_dir_fallback = False
        if dir_importers:
            importer_files |= dir_importers
            used_dir_fallback = True

        # Gather the actual ImportStatements pointing to target. Prefer the
        # precise per-edge map (BACK-542: correct even when one statement
        # resolves to several targets); fall back to resolved_paths, then to a
        # bare importer entry if neither matches.
        dependents = []
        for importer in sorted(importer_files):
            edge_stmt = self._edge_stmts.get((importer, target))
            if edge_stmt is None and used_dir_fallback:
                edge_stmt = self._edge_stmts.get((importer, dir_target))
            if edge_stmt is not None:
                dependents.append(_format_import_stmt(edge_stmt))
                continue
            matched = False
            for stmt in self._graph.files.get(importer, []):
                resolved = self._graph.resolved_paths.get(stmt.module_name)
                if resolved == target or (used_dir_fallback and resolved == dir_target):
                    dependents.append(_format_import_stmt(stmt))
                    matched = True
            if not matched:
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
        # BACK-547: undercount_possible flags that an empty result may be a lower
        # bound (intra-project imports that didn't resolve), so the renderer
        # softens the confident "nothing imports this" assertion and the ⚠ shows.
        empty = not dependents
        result['undercount_possible'] = empty and self._unresolved_intra > 0
        warnings = self._warnings(include_honest_decline=empty)
        if warnings:
            result['warning'] = warnings
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
        empty = not modules
        result['undercount_possible'] = empty and self._unresolved_intra > 0
        warnings = self._warnings(include_honest_decline=empty)
        if warnings:
            result['warning'] = warnings
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
