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
from typing import Dict, Any, List, NamedTuple, Optional, Set, Tuple

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import safe_json_dumps
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages
from ..utils.query import parse_query_params
from ..utils.path_utils import (
    is_skippable_dir,
    is_unsafe_scan_root,
    resolve_project_root,
    search_parents,
    _PACKAGE_ROOT_MARKERS,
    _VCS_ROOT_MARKERS,
    _has_package_marker,
    _has_vcs_marker,
)

# BACK-612: the marker sets and per-tier predicates now live in
# reveal.utils.path_utils (the single home shared with config/I002/D005) —
# imported above. Kept here: the back-compat union alias
# (`_PROJECT_ROOT_MARKERS`, "is there ANY marker in this one dir") and the
# `_has_project_marker` helper the depends tests import. See
# internal-docs/design/SCAN_ROOT_RESOLUTION_2026-07-09.md.
_PROJECT_ROOT_MARKERS = _PACKAGE_ROOT_MARKERS + _VCS_ROOT_MARKERS


class _ResolutionIndices(NamedTuple):
    """The per-scan indices `_build_graph` builds in its first pass over
    `files` and consumes in edge resolution. Grouped so the pass that
    produces them and the passes that read them can be separate methods
    without a wide positional hand-off (BACK-566)."""
    all_imports: List[ImportStatement]  # every extracted import, → ImportGraph
    project_namespaces: Set[str]        # declared packages/namespaces (honest-decline)
    namespace_index: Dict[str, List[Path]]        # BACK-554: namespace → declaring files
    member_index: Dict[Tuple[str, str], List[Path]]  # BACK-547/557: (pkg, symbol) → files
    zeitwerk_index: Dict[str, Path]     # BACK-557: constant-path → declaring file
    module_index: Dict[str, List[Path]]  # BACK-567: Swift module → member files


def _has_project_marker(directory: Path) -> bool:
    """True if *directory* holds a depends:// project-root marker (package or
    VCS, union of both tiers). A missing marker is a hang, not a cosmetic gap
    (BACK-515); the tiers decide *which* marker gets promoted (BACK-525). Both
    predicates now live in path_utils (BACK-612); kept here for the tests."""
    return _has_package_marker(directory) or _has_vcs_marker(directory)


def _resolve_project_root(
    target_path: Path, root_override: Optional[Path] = None
) -> Optional[Path]:
    """Resolve depends://'s scan root via the shared, ceiling-bounded resolver
    (BACK-612): tier -1 ``?root=`` override → tier 0 ``.reveal.yaml root:true``
    → tier 1 package marker → tier 2 VCS root. Returns ``None`` if nothing
    matches before the hard ceiling — ``get_structure`` then applies depends://'s
    own inferred-project fallback (BACK-525 layer 3), which is why the shared
    resolver's ``python_init_chain`` tier is left off here.
    """
    return resolve_project_root(target_path, root_override=root_override)

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
    'root': {
        'type': 'string',
        'description': (
            'Pin the scan root to DIR for this invocation (highest precedence — '
            'beats .reveal.yaml root:true, package, and VCS markers). Resolved '
            'relative to cwd; must be a directory containing the target and is '
            'refused if it is a filesystem/home/system root. Use it when the '
            'auto-detected root climbs too high — e.g. a marker-less C/C++ tree '
            'nested under a larger ancestor .git repo.'
        ),
        'examples': ["depends://src/server.c?root=src"],
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
    {
        'uri': "depends://project/src/main.c?root=project",
        'description': (
            'Pin the scan root when auto-detection over-climbs (e.g. a Makefile '
            'C project nested under a larger ancestor .git)'
        ),
        'output_type': 'module_dependents',
    },
]

_SCHEMA_NOTES = [
    'Inverts the import graph built by imports:// — same language support, same resolution',
    'Dynamic imports (importlib.import_module, __import__) are not tracked',
    'TYPE_CHECKING-only imports are excluded from edges (intentional)',
    'Results are conservative: false negatives possible, never false positives',
    'Use ?top=N on a directory to find high-coupling modules (many dependents = high impact if changed)',
    'Use depends://file.py to do impact analysis before refactoring a module',
    'Scan root: ?root=DIR > .reveal.yaml root:true > package marker > VCS root > inferred subtree',
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

        # BACK-557: convention-autoload coverage caveat prints for both empty
        # and positive results (a positive count is still a lower bound here).
        autoload_note = result.get('autoload_note')
        if autoload_note:
            print(f"{autoload_note}\n")

        if not dependents:
            if result.get('undercount_possible'):
                # BACK-547: the caveat (⚠) already printed above; do not assert
                # the confident "nothing imports this module" that contradicts it.
                print("  No dependents resolved — but see the ⚠ above: this may be incomplete.")
            else:
                print("  No dependents found (nothing imports this module)")
            same_module_note = result.get('same_module_note')
            if same_module_note:
                print()
                print(same_module_note)
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

    # BACK-557: convention-autoloading coverage caveat. When a
    # `convention_autoloaded` language (Ruby/Rails-Zeitwerk) dominates the scan
    # and the fraction of its files carrying ANY import/require statement falls
    # below this threshold, statement-based analysis structurally undercounts
    # (most intra-app edges are bare constant references with no statement).
    # Threshold grounded in the real Discourse corpus: convention-loaded trees
    # cluster ≤10% require-density (app/ 4.7%, db/ 1.8%, plugins/ 8.9%,
    # spec/ 10.2%) while explicit-require Ruby sits far higher (config/ 32%,
    # script/ 87%); 15% lands in the empirical gap. Min file count avoids
    # firing on tiny toy trees where the ratio is noise.
    _AUTOLOAD_DENSITY_THRESHOLD = 0.15
    _AUTOLOAD_MIN_FILES = 20

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
        # BACK-610: the validated ?root= override actually in effect (None when
        # not passed or rejected), plus a one-line reason when a passed ?root=
        # was rejected (surfaced via _warnings so the fallback isn't silent).
        self._root_override_used: Optional[Path] = None
        self._root_override_rejected: Optional[str] = None
        # BACK-547 honest-decline: import statements that were extracted and
        # point intra-project (per the extractor's is_intra_project_import) but
        # produced no graph edge — the false-negative risk a blast-radius
        # negative must disclose rather than assert a confident "nothing here".
        self._unresolved_intra = 0
        self._unresolved_examples: List[tuple] = []
        # BACK-557: per-scan require-statement coverage for the dominant
        # convention-autoloaded language (Ruby). total = files of that language
        # scanned; with_imports = those declaring ≥1 import/require.
        self._autoload_total = 0
        self._autoload_with_imports = 0
        # BACK-557 direction a: count of edges added purely from Zeitwerk
        # constant-path inference (no backing require/import statement).
        self._zeitwerk_edges = 0
        # BACK-565: PHP framework-constant (`define('ABSPATH', ...)`) index
        # size and the count of constant names found ambiguous (different
        # define() sites resolving to different absolute values) and
        # therefore excluded from resolution.
        self._constants_indexed = 0
        self._constants_ambiguous = 0

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
        # ceiling it can never itself become the answer to. BACK-610: an
        # explicit ?root= override (validated) takes precedence over the climb.
        root_override = self._validated_root_override(target_path)
        project_root = _resolve_project_root(target_path, root_override=root_override)
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

    def _validated_root_override(self, target_path: Path) -> Optional[Path]:
        """BACK-610: resolve and validate the ``?root=DIR`` query param, if any.

        Returns the pinned scan root (an absolute, resolved ``Path``) when the
        param is present and valid, else ``None`` — in which case resolution
        falls through to the normal tier-0..3 climb. A *passed-but-invalid*
        ``?root=`` records a one-line reason in ``self._root_override_rejected``
        (surfaced via :meth:`_warnings`) so the fallback is never silent.

        Validation (fail-closed to the auto climb, never raising):
        * resolved relative to cwd and ``~`` expanded, so a relative DIR works
          the same in CLI and MCP/service mode (the URI is what's passed in both);
        * must be an existing directory;
        * must not be an unsafe scan root (``/``, ``$HOME``, temp/system dir) —
          the same ceiling guard the climb obeys, so ``?root=`` cannot be used
          to force the catastrophic wide scan the ceiling exists to prevent;
        * must contain the target (or equal it) — a root that doesn't hold the
          target can never surface the target's dependents.

        The scan-file cap in :meth:`_build_graph` still applies to whatever root
        is pinned, so a legitimately huge pinned root is capped-and-warned, not
        silently truncated.
        """
        raw = self._query_params.get('root')
        if not raw or not isinstance(raw, str):
            return None
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve()
        if not candidate.is_dir():
            self._root_override_rejected = (
                f"?root={raw} is not an existing directory"
            )
            return None
        if is_unsafe_scan_root(candidate):
            self._root_override_rejected = (
                f"?root={raw} resolves to a filesystem/home/system root"
            )
            return None
        if not _path_is_under(target_path, candidate):
            self._root_override_rejected = (
                f"?root={raw} does not contain the target"
            )
            return None
        self._root_override_used = candidate
        return candidate

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
            'zeitwerk_edges_inferred': self._zeitwerk_edges,
            'php_constants_indexed': self._constants_indexed,
            'php_constants_ambiguous': self._constants_ambiguous,
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
        self._zeitwerk_edges = 0
        self._constants_indexed = 0
        self._constants_ambiguous = 0

        # Four phases, split out for readability/complexity (BACK-566), same
        # order and behavior as before: (1) walk the tree into `files` + a
        # basename index; (2) parse every file once into the resolution
        # indices; (3) resolve each import to graph edges; (4) add the
        # convention-only Zeitwerk edges.
        files, file_index = self._discover_files(scan_root, supported_exts)
        indices = self._build_resolution_indices(files)
        self._graph = ImportGraph.from_imports(indices.all_imports)
        self._resolve_edges(scan_root, file_index, indices)
        self._build_zeitwerk_edges(files, indices.zeitwerk_index)

    def _discover_files(
        self, scan_root: Path, supported_exts: frozenset,
    ) -> Tuple[List[Path], Dict[str, List[Path]]]:
        """Walk `scan_root` into the parse corpus + a basename index.

        BACK-498: discover files the same way ImportsAdapter._build_graph does —
        os.walk honoring SKIP_DIRECTORIES/hidden dirs (not a raw rglob, which
        both scans build artifacts/vendor dirs it shouldn't and, on a repo where
        scan_root ends up far above the real project, times out) — and build a
        basename -> [full paths] index alongside it. Package/namespace-resolved
        languages (Java, Kotlin, C#, PHP, Swift) need that index to resolve a
        dotted/qualified import to a file without their own tree walk; without
        it `resolve_import` silently fails for every such import and depends://
        reports "No dependents found" even though imports://?rank=fan-in sees
        the same edge (BACK-491 built this index for imports:// only).

        Sets ``self._scan_capped`` as a side effect (the file-count cap).
        """
        files: List[Path] = []
        file_index: Dict[str, List[Path]] = {}
        if scan_root.is_file():
            if scan_root.suffix in supported_exts:
                files.append(scan_root)
        else:
            for root, dirs, filenames in os.walk(str(scan_root)):
                dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
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
        return files, file_index

    def _build_resolution_indices(self, files: List[Path]) -> '_ResolutionIndices':
        """Parse every file in `files` once into the resolution indices.

        One pass over the parse corpus that produces everything edge
        resolution needs: the flat import list (→ ImportGraph), the
        package/namespace declaration sets, and the namespace / member /
        Zeitwerk indices. Also updates the autoload-coverage and
        PHP-constant counters as a side effect.
        """
        all_imports: List[ImportStatement] = []
        # BACK-547/544/549: the set of packages/namespaces the tree declares,
        # for honest-decline classification of package-declaring languages
        # (C#, and since this session, Java/Kotlin/PHP) — an unresolved
        # dotted import is intra-project iff the project declares a matching
        # package/namespace. Only files whose extractor supports it
        # contribute (no-op scan otherwise); Swift has no such declaration to
        # scan and stays on the conservative None verdict.
        project_namespaces: Set[str] = set()
        # BACK-554: namespace -> [declaring files], the C# edge-fanout index
        # (BACK-544) that ImportsAdapter._build_namespace_index builds but
        # depends:// never wired in — resolve_import's dotted-name match only
        # catches a namespace that coincidentally names one file (`using
        # X.Y` -> `Y.cs`); the common case, a namespace declared across
        # several files (or a file with NO local `using` at all, e.g. one
        # that relies purely on a project-wide C# 10 `global using`), needs
        # this fan-out instead. Built from `files` (every scanned file, not
        # just the ones that emit an import statement) so a zero-import leaf
        # file's own namespace declaration is still indexed — the
        # `self._graph.files`-only scope ImportsAdapter's version uses is
        # itself a sibling bug this loop found (BACK-554, fixed there too).
        namespace_index: Dict[str, List[Path]] = {}
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
        # BACK-557 direction a: constant-path -> declaring file, the Zeitwerk
        # path->constant convention index. Built from EVERY scanned file
        # under a recognized autoload root (app/<component>/...), not just
        # ones with import statements — most Zeitwerk-resolved files have
        # zero require statements by design, so gating this on
        # self._graph.files (import-derived) would miss almost all of them.
        zeitwerk_index: Dict[str, Path] = {}
        # BACK-567: module-name -> [member files], the Swift SwiftPM
        # target-membership index. Built purely from each file's PATH
        # (Sources/<Target>/** convention) — no tree-sitter parse, no Swift
        # toolchain — so `import Foo` can fan out to every file in module Foo
        # (mirroring C#'s namespace fan-out), instead of _resolve_module's
        # bare-basename match that resolves ~0% of real multi-file targets. Its
        # key set is also the in-tree module inventory is_intra_project_import
        # needs (fed via project_namespaces below) to classify `import Foo` as
        # intra-project vs an external framework — that dual use is why the
        # keys join project_namespaces rather than a separate set.
        module_index: Dict[str, List[Path]] = {}
        # BACK-565: name -> ('literal', str) | ('absolute', str), the
        # project-wide PHP framework-constant index (`define('ABSPATH',
        # __DIR__ . '/')`) that `_concat_to_import`'s `ABSPATH . WPINC .
        # '/version.php'`-shaped resolution looks up. Built to a fixed point
        # over `files` (not a single pass): real WordPress code chains
        # constants through each other (`WP_CONTENT_DIR = ABSPATH .
        # 'wp-content'`, `WP_PLUGIN_DIR = WP_CONTENT_DIR . '/plugins'`), and
        # `files` is walk-ordered, not dependency-ordered, so a constant
        # defined later in the walk than a file that references it needs a
        # second pass to resolve — capped at a small iteration count since
        # real chains are only 2-3 levels deep, never unbounded.
        constant_index, constant_ambiguous = self._build_constant_index(files)
        self._constants_indexed = len(constant_index)
        self._constants_ambiguous = len(constant_ambiguous)
        # BACK-567: explicit-`path:` target dirs from every Package.swift, built
        # once before the per-file loop so each Swift file's module lookup can
        # prefer an authoritative manifest mapping over the directory
        # convention (see _swift_module_for).
        manifest_dirs = self._build_manifest_module_dirs(files)
        for file_path in files:
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            if getattr(extractor, 'spec', None) is not None:
                file_imports = extractor.extract_imports(file_path, constant_index=constant_index)
            else:
                file_imports = extractor.extract_imports(file_path)
            all_imports.extend(file_imports)
            spec = getattr(extractor, 'spec', None)
            # BACK-557: require-statement coverage for the convention-autoloaded
            # language (Ruby). Counted over EVERY scanned file of that language,
            # including zero-import ones (which never enter self._graph.files),
            # so the density denominator is the true file count.
            if getattr(spec, 'convention_autoloaded', False):
                self._autoload_total += 1
                if file_imports:
                    self._autoload_with_imports += 1
            if getattr(spec, 'zeitwerk_convention', False):
                const_path = _zeitwerk_constant_path(file_path)
                if const_path:
                    # First declaration wins on a naming collision (two
                    # autoload roots producing the same constant is a
                    # pre-existing Zeitwerk-app misconfiguration, not
                    # something to guess between).
                    zeitwerk_index.setdefault(const_path, file_path)
            if getattr(spec, 'module_dir_convention', None):
                # BACK-567: index this file under its SwiftPM target. An explicit
                # manifest `path:` (manifest_dirs) wins over the directory
                # convention (real case: GraphAPI's `path: "./Sources"`); the
                # convention is the fallback for the common default layout.
                # Every scanned file of the module participates, including
                # zero-import ones, so `import Foo` fans out to the whole target.
                # The module name also joins project_namespaces as the in-tree
                # module inventory is_intra_project_import checks against.
                module_name = self._swift_module_for(extractor, file_path, manifest_dirs)
                if module_name:
                    module_index.setdefault(module_name, []).append(file_path)
                    project_namespaces.add(module_name)
            if getattr(spec, 'resolve_namespaces', False) or getattr(spec, 'package_node_types', None):
                declared = extractor.extract_namespaces(file_path)
                project_namespaces.update(declared)
                if getattr(spec, 'resolve_namespaces', False):
                    for ns in declared:
                        namespace_index.setdefault(ns, []).append(file_path)
                if getattr(spec, 'member_symbol_fallback', False) and declared:
                    for symbol in extractor.extract_top_level_members(file_path):
                        for ns in declared:
                            member_index.setdefault((ns, symbol), []).append(file_path)
                if getattr(spec, 'container_member_fallback', False) and declared:
                    # BACK-557 Scala measurement loop: `import a.b.container.member`
                    # where `container` is a lowerCamelCase top-level object (e.g.
                    # `object helpers`) that BACK-551's Uppercase-gated peel
                    # deliberately refuses to reach. Synthesize the same
                    # (package, symbol) shape member_symbol_fallback uses, keyed
                    # under the container's own qualified name
                    # (`declared_package<sep>containerName`), so
                    # resolve_member_targets's existing split-on-last-component
                    # lookup finds it with no further changes.
                    sep = spec.module_separator or ''
                    for container_name, symbol in extractor.extract_container_members(file_path):
                        for ns in declared:
                            key = (f'{ns}{sep}{container_name}', symbol)
                            member_index.setdefault(key, []).append(file_path)

        return _ResolutionIndices(
            all_imports=all_imports,
            project_namespaces=project_namespaces,
            namespace_index=namespace_index,
            member_index=member_index,
            zeitwerk_index=zeitwerk_index,
            module_index=module_index,
        )

    @staticmethod
    def _build_manifest_module_dirs(files: List[Path]) -> List[Tuple[Path, str]]:
        """BACK-567: (resolved_source_dir, module_name) for every build-manifest
        target that sets an EXPLICIT `path:`, across every Package.swift in the
        scan.

        Only explicit-path targets are recorded — a default-layout target
        (`Sources/<name>/`) is already handled correctly by the directory
        convention (:meth:`_GenericTreeSitterImportExtractor.module_for_file`),
        so re-deriving it here would be redundant and would need the target's
        on-disk directory name (lost to module-name sanitization) anyway. The
        explicit path is resolved against the manifest's own directory, so
        `./Sources`, `./GraphAPITestMocks`, `../Sibling`, and `Sources/Foo` all
        work. Sorted longest-path-first so :meth:`_swift_module_for`'s
        first-containing-match is a longest-prefix match (a nested target dir
        wins over an ancestor target dir)."""
        dirs: List[Tuple[Path, str]] = []
        for f in files:
            spec = getattr(get_extractor(f), 'spec', None)
            manifest = getattr(spec, 'manifest_filename', None)
            if not manifest or f.name != manifest:
                continue
            extractor = get_extractor(f)
            pkg_dir = f.parent
            for name, path, _is_test in extractor.extract_manifest_targets(f):
                if not path:
                    continue  # default layout — the directory convention handles it
                dirs.append(((pkg_dir / path).resolve(), name))
        dirs.sort(key=lambda d: len(d[0].parts), reverse=True)
        return dirs

    @staticmethod
    def _swift_module_for(
        extractor, file_path: Path, manifest_dirs: List[Tuple[Path, str]],
    ) -> Optional[str]:
        """The module a Swift file belongs to: an explicit-`path:` manifest
        target that contains it (longest prefix), else the directory convention
        (BACK-567)."""
        resolved = file_path.resolve()
        for abs_dir, module_name in manifest_dirs:
            if resolved == abs_dir or abs_dir in resolved.parents:
                return module_name
        return extractor.module_for_file(file_path)

    def _resolve_edges(
        self, scan_root: Path, file_index: Dict[str, List[Path]],
        indices: '_ResolutionIndices',
    ) -> None:
        """Resolve every extracted import into dependency (and reverse_deps)
        edges, one file at a time."""
        for file_path, imports in self._graph.files.items():
            extractor = get_extractor(file_path)
            if not extractor:
                continue

            base_path = file_path.parent
            # BACK-621 GDScript: the `!= base_path` skip was a harmless dedup
            # for every resolver that also tries base_path itself first (the
            # `_resolve_path_target` roots list is `[base_path] + search_paths`)
            # — until `project_relative_prefix` (GDScript `res://`), the one
            # resolver that deliberately never falls back to base_path at all
            # (project-root-relative, not file-relative). For an importer
            # sitting directly in scan_root (a project's own root-level
            # `game.gd`/`main.gd`/`test.gd`), that made extra_paths empty and
            # every `res://` import in that file silently unresolvable — found
            # via the godot-demo-projects oracle loop (3 of 3 sampled
            # root-level preload/load edges missed). Always including
            # scan_root costs nothing for the other resolvers (base_path is
            # already tried first, so this is just a harmless duplicate root).
            extra_paths = [scan_root] if scan_root.is_dir() else []
            # Mirrors ImportsAdapter._build_graph's gating (BACK-491): only
            # generic (spec-based) extractors accept file_index.
            uses_file_index = getattr(extractor, 'spec', None) is not None
            for stmt in imports:
                if stmt.is_type_checking:
                    continue
                self._resolve_statement_edges(
                    stmt, file_path, extractor, base_path, extra_paths,
                    uses_file_index, file_index, indices)

    def _resolve_statement_edges(
        self, stmt: 'ImportStatement', file_path: Path, extractor,
        base_path: Path, extra_paths: List[Path], uses_file_index: bool,
        file_index: Dict[str, List[Path]], indices: '_ResolutionIndices',
    ) -> None:
        """Resolve a single import statement, walking the fallback cascade:
        direct resolution → namespace index (BACK-554) → member index
        (BACK-547/557) → honest-decline classification (BACK-547)."""
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
        spec = getattr(extractor, 'spec', None)
        if not added and indices.namespace_index and getattr(spec, 'resolve_namespaces', False):
            # BACK-554: the single-file dotted match above only catches a
            # namespace that coincidentally names one matching file — the
            # common case (a namespace declared across several files, or
            # a file reachable only via a project-wide `global using`)
            # needs the namespace index instead, fanning out to every
            # declaring file (mirrors ImportsAdapter._resolve_dependencies,
            # BACK-544).
            for resolved in extractor.resolve_namespace_targets(stmt, indices.namespace_index):
                if resolved != file_path:
                    self._graph.add_dependency(file_path, resolved)
                    self._edge_stmts[(file_path, resolved)] = stmt
                    added = True
        if not added and indices.member_index and (
                getattr(spec, 'member_symbol_fallback', False)
                or getattr(spec, 'container_member_fallback', False)):
            # BACK-547 Kotlin measurement loop: `import a.b.foo` for a
            # top-level fun/val/var — the direct dotted match above
            # looked for `foo.kt` and failed, and BACK-551's
            # enclosing-class peel can't help either (there is no
            # enclosing type in the import path to peel down to).
            # BACK-557 Scala measurement loop: same fallback also
            # covers `import a.b.container.member` where `container`
            # is a lowerCamelCase object BACK-551's peel refuses to
            # reach. Fall back to the content-scanned member index.
            for resolved in extractor.resolve_member_targets(stmt, indices.member_index):
                if resolved != file_path:
                    self._graph.add_dependency(file_path, resolved)
                    self._edge_stmts[(file_path, resolved)] = stmt
                    added = True
        if indices.module_index and getattr(spec, 'module_dir_convention', None):
            # BACK-567 Swift: `import Foo` names a whole SwiftPM target, not a
            # file. Fan out to every file in module Foo via the path-derived
            # module index — the same module→many-files shape C#'s namespace
            # index uses. Deliberately NOT gated on `not added`: the direct
            # bare-basename match above resolves `import Foo` iff a UNIQUE
            # `Foo.swift` exists (real case: ServerDrivenUI/ServerDrivenUI.swift),
            # which is just one of the target's files — letting that pre-empt
            # the fan-out would under-report the module to a single file. The
            # fan-out is a superset (it includes that Foo.swift) and reverse_deps
            # is set-keyed, so unioning is idempotent.
            for resolved in extractor.resolve_module_targets(stmt, indices.module_index):
                if resolved != file_path:
                    self._graph.add_dependency(file_path, resolved)
                    self._edge_stmts.setdefault((file_path, resolved), stmt)
                    added = True
        if not added:
            # BACK-547 honest-decline: an extracted import that produced
            # no edge is only a false-negative risk if it points
            # intra-project. External (stdlib/dep) imports correctly have
            # no in-tree edge; None means the extractor can't tell, and
            # we conservatively don't count it (never cry wolf).
            verdict = extractor.is_intra_project_import(
                stmt, base_path, search_paths=extra_paths,
                project_namespaces=indices.project_namespaces)
            if verdict is True:
                self._unresolved_intra += 1
                if len(self._unresolved_examples) < 5:
                    self._unresolved_examples.append((file_path, stmt))

    def _build_zeitwerk_edges(
        self, files: List[Path], zeitwerk_index: Dict[str, Path],
    ) -> None:
        """Add Zeitwerk convention-inferred edges (BACK-557 direction a).

        A second pass over EVERY scanned file (not self._graph.files — most
        Zeitwerk-resolved files have no import statement, so they never
        entered that import-derived dict) whose extractor opts in via
        spec.zeitwerk_convention. Exact-match only against zeitwerk_index
        (built from the tree's own file layout): a reference that
        doesn't land on a real in-tree file's conventional constant name
        is simply not added, never guessed at — the same honest-skip
        contract every other resolver in this module holds to.
        """
        if not zeitwerk_index:
            return
        for file_path in files:
            extractor = get_extractor(file_path)
            if extractor is None:
                continue
            spec = getattr(extractor, 'spec', None)
            if not getattr(spec, 'zeitwerk_convention', False):
                continue
            for line_no, const_path in extractor.extract_constant_references(file_path):
                target = zeitwerk_index.get(const_path)
                if target is None or target == file_path:
                    continue
                self._graph.add_dependency(file_path, target)
                self._zeitwerk_edges += 1
                if (file_path, target) not in self._edge_stmts:
                    # No real statement backs this edge — synthesize one
                    # so file-dependents display still shows a module
                    # name and line rather than falling through to the
                    # generic 'unknown'-type dependent entry.
                    self._edge_stmts[(file_path, target)] = ImportStatement(
                        file_path=file_path,
                        line_number=line_no,
                        module_name=const_path,
                        imported_names=[],
                        is_relative=False,
                        import_type='zeitwerk_convention',
                        skip_unused=True,
                    )

    @staticmethod
    def _build_constant_index(
        files: List[Path],
    ) -> Tuple[Dict[str, Tuple[str, str]], Set[str]]:
        """BACK-565: project-wide PHP `define()` constant index, to a fixed
        point.

        Real WordPress code chains framework constants through each other
        (`WP_CONTENT_DIR = ABSPATH . 'wp-content'`, `WP_PLUGIN_DIR =
        WP_CONTENT_DIR . '/plugins'`), and `files` is walk order, not
        dependency order — a single pass would miss any constant defined in
        a file visited after the one that references it. Re-scanning with
        the previous pass's result as `known_constants` converges once no
        pass changes the index; real chains measured at most 2-3 levels deep
        (ABSPATH -> WP_CONTENT_DIR -> WP_PLUGIN_DIR), so 6 passes is a wide
        safety margin, not a tuned constant — this is a bounded fixed point,
        not an unbounded loop.

        Ambiguity (BACK-565's explicit requirement): if a constant name
        resolves to more than one *distinct* value across `define()` sites
        in the corpus (confirmed real shape — WordPress's own `ABSPATH` is
        defined via `__DIR__ . '/'` in `wp-load.php` at the project root and
        via `dirname( __DIR__ ) . '/'` in `wp-admin/*.php`, but both
        resolve to the *same* real absolute directory, so they agree and
        are NOT ambiguous), the name is excluded from the returned index
        entirely — never guessed at, and never left holding an arbitrary
        "first one wins" value. Returns ``(index, ambiguous_names)`` so the
        caller can report both counts.

        Performance: `extract_constant_defines` re-parses its file from
        scratch every call (no analyzer cache in this module), so scanning
        every file in a large tree up to 6 times would multiply an already
        non-trivial parse cost. A file with no `define(`-family callee
        anywhere in its raw text can never contribute a constant, so a cheap
        substring pre-filter (real corpus: 89/1927 WordPress files call
        `define(` at all) narrows the fixed-point loop to the files that can
        possibly matter, before any tree-sitter parse — same "cheap check
        before the expensive one" shape as `is_skippable_dir`.
        """
        candidate_files: List[Path] = []
        for file_path in files:
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            spec = getattr(extractor, 'spec', None)
            call_names = getattr(spec, 'constant_define_call_names', None)
            if not call_names:
                continue
            try:
                text = file_path.read_text(errors='ignore')
            except OSError:
                continue
            # `name + '('` (not bare `name`), so `defined(` — extremely
            # common in real WordPress code checking a constant it doesn't
            # declare — doesn't false-positive the filter into scanning
            # files that can never contain a `define(` call. PHP call syntax
            # never puts whitespace between a callee name and its `(`.
            if any(f'{name}(' in text for name in call_names):
                candidate_files.append(file_path)

        index: Dict[str, Tuple[str, str]] = {}
        ambiguous: Set[str] = set()
        for _ in range(6):
            candidates: Dict[str, Set[Tuple[str, str]]] = {}
            for file_path in candidate_files:
                extractor = get_extractor(file_path)
                if not extractor:
                    continue
                for name, value in extractor.extract_constant_defines(file_path, index):
                    candidates.setdefault(name, set()).add(value)
            new_index: Dict[str, Tuple[str, str]] = {}
            ambiguous: Set[str] = set()
            for name, values in candidates.items():
                if len(values) == 1:
                    new_index[name] = next(iter(values))
                else:
                    ambiguous.add(name)
            if new_index == index:
                return new_index, ambiguous
            index = new_index
        return index, ambiguous

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
        if self._convention_autoload_note():
            known_limits.append(
                f'{self._autoload_with_imports}/{self._autoload_total} Ruby files declare any '
                'require — BACK-557, convention-based autoloading (Zeitwerk) suspected, '
                'require-based dependents may significantly undercount (positive results too)')
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

        BACK-610: the advice is now honest for the case that actually breaks.
        The old wording ("Scope depends:// to a narrower path") is *impossible*
        for a single-file target — you can't narrow a single file, and the real
        cause is the scan root climbing above the file's project (an ancestor
        .git). For a file target, name the levers that actually fix it: ``?root=``
        or a ``.reveal.yaml root:true`` marker. If a ``?root=`` was already in
        effect and the cap still fired, the pinned root is genuinely over the cap,
        so don't loop back to advice they already followed.
        """
        if not self._scan_capped:
            return ''
        root = self._scan_root
        base = (
            f"⚠ Scan capped at {self._SCAN_FILE_CAP:,} files under {root} — "
            "results may be incomplete."
        )
        if self._root_override_used is not None:
            return f"{base} This pinned ?root= exceeds the scan cap even as scoped."
        if self._target_path is not None and self._target_path.is_file():
            return (
                f"{base} Can't narrow a single-file target — the scan root climbed "
                "above this file's project. Pin it with depends://…?root=DIR or a "
                "'.reveal.yaml' containing 'root: true' at the project root."
            )
        return (
            f"{base} Scope depends:// to a narrower path, or pin the root with "
            "?root=DIR (or a '.reveal.yaml' with 'root: true')."
        )

    def _root_override_warning(self) -> str:
        """BACK-610: one-line disclosure when a passed ``?root=`` was rejected
        and validation fell back to auto-detection — so the silent fallback
        doesn't hand back a scope the user didn't ask for without saying why."""
        if not self._root_override_rejected:
            return ''
        return (
            f"⚠ {self._root_override_rejected} — ignored, using the auto-detected "
            "scan root instead."
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

    def _same_module_note(self, target: Path) -> str:
        """BACK-560/567: unconditional informational note framing what a Swift
        file's dependent list does and doesn't mean. Two distinct truths:

        1. **Same-module (same-target) references are invisible** (BACK-560) —
           Swift compiles a target together, so a sibling file uses this file's
           declarations with no `import` statement to extract. Not an
           undercount from failed resolution; a class of edge that has no
           syntax at all. Deliberately NOT the ⚠ honest-decline signal (keyed
           on _unresolved_intra, which never increments here — nothing was
           extracted to fail).

        2. **Cross-module dependents shown are module-level** (BACK-567) — an
           `import Foo` names the whole module Foo, so every file importing
           this file's module is listed as a dependent, whether or not it uses
           *this specific file*. The count is an honest ceiling at Swift's
           import granularity (the module), not file-precise like Java's."""
        extractor = get_extractor(target)
        spec = getattr(extractor, 'spec', None)
        if not getattr(spec, 'same_module_undetectable', False):
            return ''
        return (
            "ℹ This is a Swift file. Swift's import granularity is the module/target, "
            "not the file, so this list is module-level: (1) same-module siblings use "
            "this file's declarations with NO `import` statement, so they can never "
            "appear here (not a failed resolution — a class of edge with no syntax); "
            "(2) any dependent shown imports this file's whole module, not necessarily "
            "this specific file. Treat the count as an import-granularity ceiling, not "
            "a file-precise dependent set."
        )

    def _convention_autoload_note(self) -> str:
        """BACK-557: project-level coverage caveat for a convention-autoloaded
        language (Ruby/Rails-Zeitwerk). Fires when that language dominates the
        scan and require-statement density is below threshold — most intra-app
        edges are bare constant references with no statement to extract, so
        depends:// structurally undercounts. Unlike the ⚠ honest-decline (which
        is keyed on failed *resolution* of an extracted import and only fires on
        empty results), this fires on positive results too: a non-empty answer
        is still a lower bound when 90%+ of edges were never expressible as a
        require in the first place. Returns '' when the signal doesn't apply."""
        if self._autoload_total < self._AUTOLOAD_MIN_FILES:
            return ''
        density = self._autoload_with_imports / self._autoload_total
        if density >= self._AUTOLOAD_DENSITY_THRESHOLD:
            return ''
        return (
            f"ℹ Only {density:.0%} of the {self._autoload_total} Ruby files scanned declare any "
            "require/require_relative — convention-based autoloading (Rails/Zeitwerk maps file "
            "paths to constant names, resolving bare references like `Topic` with no statement) "
            "is likely. depends:// only sees require-based edges, so intra-project dependents "
            "here may be significantly undercounted regardless of the count shown."
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
        parts = [
            self._root_override_warning(),
            self._scan_cap_warning(),
            self._root_inferred_warning(),
        ]
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
        if empty:
            note = self._same_module_note(target)
            if note:
                result['same_module_note'] = note
        autoload_note = self._convention_autoload_note()
        if autoload_note:
            result['autoload_note'] = autoload_note
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
        autoload_note = self._convention_autoload_note()
        if autoload_note:
            result['autoload_note'] = autoload_note
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


def _camelize(segment: str) -> str:
    """Rails ``String#camelize``-equivalent for one path segment: default
    inflection only (``foo_bar`` -> ``FooBar``). Does not consult
    ``config/initializers/inflections.rb`` overrides (acronyms like ``HTTP``
    camelize to ``Http``, not ``HTTP``) — a recall gap, not a correctness
    one: a wrong guess here only ever means a missed edge (BACK-557's
    zeitwerk_convention index is exact-match only, see
    :func:`_zeitwerk_constant_path`), never a fabricated one.
    """
    return ''.join(part[:1].upper() + part[1:] for part in segment.split('_') if part)


def _zeitwerk_constant_path(file_path: Path) -> Optional[str]:
    """The constant Zeitwerk would resolve ``file_path`` to, or ``None`` if
    it isn't under a recognized autoload root.

    Scope (BACK-557 direction a): only ``app/<component>/...`` trees are
    treated as autoload roots — each direct child of ``app/`` (``models``,
    ``controllers``, ``jobs``, ...) is by convention its own Zeitwerk root,
    so ``app/models/foo/bar.rb`` maps to ``Foo::Bar`` with the ``app/models``
    prefix dropped. This is the exact shape measured on the real Discourse
    corpus (the ruby-autoload-oracle README's low-density evidence) and
    deliberately narrower than Zeitwerk's full ``lib/``/custom-root
    configurability — a project's actual ``config/application.rb`` autoload
    paths aren't visible to a structural file scan, so widening past the one
    universal Rails convention would trade a bounded, principled scope for
    guesses. ``concerns/`` collapsing (Rails' default autoload_paths include
    each ``app/*/concerns`` directly, so ``app/models/concerns/x.rb`` is
    ``X``, not ``Concerns::X``) is also not modeled — another recall-only
    gap, not a soundness one.
    """
    parts = file_path.parts
    try:
        app_idx = len(parts) - 1 - parts[::-1].index('app')
    except ValueError:
        return None
    if app_idx + 1 >= len(parts) - 1:
        return None  # 'app' with no component subdir before the filename
    root_end = app_idx + 2  # 'app', '<component>' — both dropped from the constant
    relative_parts = parts[root_end:]
    if not relative_parts:
        return None
    *dirs, filename = relative_parts
    stem = Path(filename).stem
    segments = [*dirs, stem]
    if not segments:
        return None
    return '::'.join(_camelize(seg) for seg in segments)
