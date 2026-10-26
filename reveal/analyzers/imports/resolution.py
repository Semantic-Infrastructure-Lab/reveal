"""Project-wide import resolution: the fallback cascade over one scan root (BACK-1054).

Moved from ``adapters/depends.py`` (slice S1 of folding depends://, deps:// and
calls://?modules into imports://), unchanged in behavior. One build walks the scan root
(``service.discover``), parses every file once into the resolution indices (namespaces,
top-level members, Swift modules, Zeitwerk constant paths, PHP ``define()`` constants,
gemspec load-path roots), resolves every import through the cascade (direct, namespace,
member, module), adds the Zeitwerk convention edges, and counts what it could not resolve
(the honest-decline counters). The answer is a :class:`ProjectResolution` record; the scan
root, the scan cap and everything a caller prints from the record stay with the caller.
"""
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set, Tuple, cast

from . import service
from .base import get_extractor
from .file_index import load_path_manifests
from .generic import RubyImportExtractor
from .types import ImportGraph, ImportStatement
from .._capability_table import depends_intra_project_classification_supported
from ...utils.path_utils import (
    hidden_entries_warning,
    is_unsafe_scan_root,
    resolve_project_root,
    search_parents,
    failure_of,
)
from ...utils.query_control import BudgetAccounting, ScanBudget
from ...reveal_types import PathFailure


# Where a scan root came from, in the climb's precedence order: a validated ``?root=``, then
# the tiers of ``resolve_project_root`` (``.reveal.yaml root: true``, the nearest package
# marker, the nearest VCS root), then the inferred fallback when nothing matched before the
# ceiling (BACK-525 layer 3). ``path``: the caller asked for the requested path itself.
ROOT_SOURCES = ('root_param', 'reveal_yaml', 'package_marker', 'vcs', 'inferred', 'path')

# Which cascade stage found an edge (ImportGraph.edge_via): the import resolved to the file
# directly, or through the PHP constant index (BACK-565), the namespace fan-out (BACK-554), the
# member index (BACK-547/557/669), the Swift module fan-out (BACK-567) or the Zeitwerk naming
# convention (BACK-557, no statement behind it). Module and convention edges name a module or a
# naming rule, not a file the importer loads, so the cycle views leave them out (VIA_NOT_CYCLES).
VIA_DIRECT, VIA_CONSTANT, VIA_NAMESPACE, VIA_MEMBER, VIA_MODULE, VIA_CONVENTION = (
    'direct', 'constant', 'namespace', 'member', 'module', 'convention')
VIAS = (VIA_DIRECT, VIA_CONSTANT, VIA_NAMESPACE, VIA_MEMBER, VIA_MODULE, VIA_CONVENTION)

# The languages (registry.language_for_extension) whose import edges a recall oracle scores in
# the CI recall gate (scripts/recall_gate.py over tests/corpus/manifest.yaml's ``recall:``
# entries; tests/test_imports_importers_back1054.py pins this set to the manifest). An answer
# with edges from any other language names it as not gated: its counts are unmeasured, whatever
# the cascade stage that found them (plan rule 8).
IMPORT_RECALL_GATED = frozenset({'c', 'cpp', 'go', 'java', 'javascript', 'python', 'rust', 'typescript', 'tsx'})


@dataclass(frozen=True)
class ScanRoot:
    """The directory one request resolves imports at, and why (BACK-525, BACK-610)."""
    root: Path
    source: str
    # The validated ``?root=`` in effect, or the one-line reason a passed one was refused
    # (the climb then decided, and the presenter says so).
    override_used: Optional[Path] = None
    override_rejected: Optional[str] = None

    @property
    def inferred(self) -> bool:
        return self.source == 'inferred'


def path_is_under(path: Path, directory: Path) -> bool:
    """True if path is inside directory (or is directory itself); lexical, both resolved."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def file_importers(graph: ImportGraph, statements: Dict[Tuple[Path, Path], ImportStatement],
                   target: Path) -> List[Tuple[Path, Tuple[Path, Path], Optional[ImportStatement]]]:
    """Who imports the file ``target``, sorted: each importer, the edge that names it and the statement
    behind that edge (``ProjectResolution.edge_statements``; None without one). A package-granularity
    language (Go) resolves an import to the package directory, so importers of ``target``'s directory
    count too (BACK-553); a file is never its own importer. The one listing imports://?importers=FILE
    and depends://FILE present (BACK-1054 S6)."""
    sources = set(graph.reverse_deps.get(target, ()))
    sources |= graph.reverse_deps.get(target.parent, set())
    sources.discard(target)
    rows = []
    for src in sorted(sources):
        key = (src, target) if (src, target) in graph.edge_scopes else (src, target.parent)
        rows.append((src, key, statements.get(key)))
    return rows


def _validated_root(target: Path, raw: Any) -> Tuple[Optional[Path], Optional[str]]:
    """BACK-610: the ``?root=DIR`` pin, or why it was refused (fail-closed to the climb).

    Resolved against cwd with ``~`` expanded, so a relative DIR works the same in CLI and
    MCP; it must be an existing directory, not a filesystem/home/system root (the ceiling
    the climb obeys), and must contain the target.
    """
    if not raw or not isinstance(raw, str):
        return None, None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    if not candidate.is_dir():
        return None, f"?root={raw} is not an existing directory"
    if is_unsafe_scan_root(candidate):
        return None, f"?root={raw} resolves to a filesystem/home/system root"
    if not path_is_under(target, candidate):
        return None, f"?root={raw} does not contain the target"
    return candidate, None


def _marker_tier(target: Path, root: Path) -> str:
    """Which tier of ``resolve_project_root`` produced ``root`` (each probe is one cached climb)."""
    if resolve_project_root(target, use_package_markers=False, use_vcs=False) == root:
        return 'reveal_yaml'
    if resolve_project_root(target, honor_reveal_root=False, use_vcs=False) == root:
        return 'package_marker'
    return 'vcs'


def choose_scan_root(target: Path, raw_root: Any = None) -> ScanRoot:
    """The project root a request about ``target`` resolves at: ``?root=`` (validated), else
    the ceiling-bounded marker climb, else the inferred subtree (BACK-525 layer 3: the target
    directory, or for a file its nearest ``src`` ancestor or its parent, BACK-498).

    Moved from depends:// so imports:// climbs the same way (BACK-1054); the presenter keeps
    the wording of every disclosure built from the record.
    """
    override, rejected = _validated_root(target, raw_root)
    if override is not None:
        return ScanRoot(override, 'root_param', override_used=override)
    root = resolve_project_root(target)
    if root is not None:
        return ScanRoot(root, _marker_tier(target, root), override_rejected=rejected)
    if target.is_dir():
        return ScanRoot(target, 'inferred', override_rejected=rejected)
    src_root = search_parents(target, lambda p: p.name == 'src')
    return ScanRoot(src_root if src_root else target.parent, 'inferred', override_rejected=rejected)


@dataclass
class ProjectResolution:
    """Everything one cascade build resolved for a scan root, before presentation."""
    scan_root: Optional[Path] = None
    graph: Optional[ImportGraph] = None
    # BACK-542: (importer, target) -> the exact ImportStatement that produced the edge, so
    # display resolves the right import line even when one statement resolves to several
    # targets (`from pkg import a, b`). Zeitwerk edges carry a synthesized statement.
    edge_statements: Dict[Tuple[Path, Path], ImportStatement] = field(default_factory=dict)
    capped: bool = False
    scan_accounting: BudgetAccounting = field(default_factory=lambda: ScanBudget(None).accounting(0))
    traversal_failures: Tuple[PathFailure, ...] = ()
    # A scan whose walk hid every candidate says so (BACK-2065).
    scope_hidden: Optional[Dict[str, Any]] = None
    # BACK-1598: files whose extractor set parse_failed, disclosed once.
    files_failed: List[str] = field(default_factory=list)
    # BACK-547 honest-decline: import statements that were extracted and point
    # intra-project (per the extractor's is_intra_project_import) but produced no graph
    # edge -- the false-negative risk a blast-radius negative must disclose rather than
    # assert a confident "nothing here".
    unresolved_intra: int = 0
    unresolved_examples: List[Tuple[Path, ImportStatement]] = field(default_factory=list)
    # BACK-1093: languages seen among unresolved imports whose extractor has no real
    # True/False intra-project classification at all (always None) -- for these,
    # `unresolved_intra` staying low/zero says nothing about actual undercount risk.
    unclassifiable_languages: Set[str] = field(default_factory=set)
    # BACK-557: require-statement coverage for the convention-autoloaded language (Ruby).
    # total = files of that language scanned; with_imports = those declaring >=1 import.
    autoload_total: int = 0
    autoload_with_imports: int = 0
    # BACK-557 direction a: edges added purely from Zeitwerk constant-path inference.
    zeitwerk_edges: int = 0
    # BACK-565: PHP framework-constant (`define('ABSPATH', ...)`) index size and the count
    # of constant names found ambiguous (different define() sites resolving to different
    # absolute values) and therefore excluded from resolution.
    constants_indexed: int = 0
    constants_ambiguous: int = 0


class _ResolutionIndices(NamedTuple):
    """The per-scan indices the first pass over `files` builds and edge resolution
    consumes. Grouped so the pass that produces them and the passes that read them can be
    separate methods without a wide positional hand-off (BACK-566)."""
    all_imports: List[ImportStatement]  # every extracted import, → ImportGraph
    project_namespaces: Set[str]        # declared packages/namespaces (honest-decline)
    namespace_index: Dict[str, List[Path]]        # BACK-554: namespace → declaring files
    member_index: Dict[Tuple[str, str], List[Path]]  # BACK-547/557: (pkg, symbol) → files
    zeitwerk_index: Dict[str, Path]     # BACK-557: constant-path → declaring file
    module_index: Dict[str, List[Path]]  # BACK-567: Swift module → member files
    load_path_roots: List[Path]         # BACK-669: extra gemspec-registered lib/ search roots


class ResolutionInputs(NamedTuple):
    """The project-wide inputs per-file extraction and indexing read (``ProjectResolver.prepare``).
    Plain data, so they travel to pool workers."""
    constant_index: Dict[str, Tuple[str, str]]  # BACK-565: PHP define() constants, ambiguous ones excluded
    constants_ambiguous: int
    manifest_dirs: List[Tuple[Path, str]]       # BACK-567: explicit-path Package.swift targets
    manifest_target_names: Set[str]             # BACK-669: every declared target name
    load_path_roots: List[Path]                 # BACK-669: gemspec lib/ roots


@dataclass
class FileEntry:
    """One file's part of the cascade's indices, made where the file is parsed (``index_file``).
    Plain data, so a pool worker can return it."""
    imports: List[ImportStatement]
    parse_failed: bool = False
    # BACK-557: None when the language is not convention-autoloaded, else whether the file
    # declares any import (the require-density numerator and denominator).
    autoloaded: Optional[bool] = None
    zeitwerk_path: Optional[str] = None          # BACK-557: the constant Zeitwerk maps it to
    module_name: Optional[str] = None            # BACK-567: its SwiftPM target
    declared: Tuple[str, ...] = ()               # namespaces/packages it declares (honest-decline)
    namespace_keys: Tuple[str, ...] = ()         # BACK-554: the namespaces it joins the fan-out under
    member_keys: Tuple[Tuple[str, str], ...] = ()  # BACK-547/557/669: (package, symbol) keys, in order


def extract_file(file_path: Path, extractor: Any, constant_index: Dict[str, Tuple[str, str]]) -> List[ImportStatement]:
    """A file's imports as the cascade reads them: a spec-based extractor gets the project's PHP
    constant index (BACK-565; a language that never reads it answers as without it)."""
    if getattr(extractor, 'spec', None) is not None:
        return cast(List[ImportStatement], extractor.extract_imports(file_path, constant_index=constant_index))
    return cast(List[ImportStatement], extractor.extract_imports(file_path))


def _member_keys(file_path: Path, extractor: Any, spec: Any, declared: List[str]) -> List[Tuple[str, str]]:
    """BACK-547 Kotlin measurement loop: (package, symbol) for each top-level free function or
    property (`import a.b.foo` has no enclosing type to peel to). BACK-557 Scala: a lowerCamelCase
    top-level object's members keyed under `package<sep>container` (BACK-551's Uppercase-gated
    peel refuses to reach them). BACK-669 C# recall loop: `using static Foo.Bar.Type;` names a
    type one component past any declared namespace. All three share resolve_member_targets'
    (namespace, symbol) shape; gated per language by the spec flags."""
    keys: List[Tuple[str, str]] = []
    if not declared:
        return keys
    if getattr(spec, 'member_symbol_fallback', False):
        keys += [(ns, symbol) for symbol in extractor.extract_top_level_members(file_path) for ns in declared]
    if getattr(spec, 'container_member_fallback', False):
        sep = getattr(spec, 'module_separator', None) or ''
        keys += [(f'{ns}{sep}{container}', symbol)
                 for container, symbol in extractor.extract_container_members(file_path) for ns in declared]
    if getattr(spec, 'namespaced_type_fallback', False):
        keys += [(ns, typename) for typename in extractor.extract_namespaced_type_names(file_path) for ns in declared]
    return keys


def index_file(file_path: Path, extractor: Any, imports: List[ImportStatement],
               manifest_dirs: List[Tuple[Path, str]]) -> FileEntry:
    """One file's contribution to every cascade index (BACK-919's per-file loop body, as data):
    autoload coverage over every file of the language, including zero-import ones (BACK-557);
    its Zeitwerk constant path; its Swift module (an explicit manifest `path:` wins over the
    directory convention, BACK-567); the namespaces it declares and the member keys under them."""
    spec = getattr(extractor, 'spec', None)
    entry = FileEntry(imports=imports)
    if getattr(spec, 'convention_autoloaded', False):
        entry.autoloaded = bool(imports)
    if getattr(spec, 'zeitwerk_convention', False):
        entry.zeitwerk_path = _zeitwerk_constant_path(file_path)
    if getattr(spec, 'module_dir_convention', None):
        entry.module_name = ProjectResolver._swift_module_for(extractor, file_path, manifest_dirs)
    if getattr(spec, 'resolve_namespaces', False) or getattr(spec, 'package_node_types', None):
        declared = list(extractor.extract_namespaces(file_path))
        entry.declared = tuple(declared)
        if getattr(spec, 'resolve_namespaces', False):
            entry.namespace_keys = tuple(declared)
        entry.member_keys = tuple(_member_keys(file_path, extractor, spec, declared))
    entry.parse_failed = bool(getattr(extractor, 'parse_failed', False))
    return entry


def resolve_project(scope: service.ScanScope) -> ProjectResolution:
    """One cascade build of ``scope.root``: the walk is capped at ``scope.cap`` source files and
    judges what it hid at ``scope.focus``; only files with an extension in ``scope.extensions``
    are parsed (resolution targets stay extension-agnostic)."""
    return ProjectResolver(cap=scope.cap, focus=scope.focus).resolve(scope.root, scope.extensions)


class ProjectResolver:
    """The cascade's phases over one scan root; ``resolve`` runs them in order."""

    def __init__(self, cap: Optional[int] = None, focus: Optional[Path] = None):
        self._cap = cap
        self._focus = focus
        self.result = ProjectResolution()
        self._graph = ImportGraph()
        self._ruby_inventory_roots_seen: Set[Path] = set()

    def resolve(self, scan_root: Path, supported_exts: frozenset) -> ProjectResolution:
        """Build the import graph of ``scan_root``.

        ``supported_exts`` (BACK-525 layer 4) restricts the *parse corpus* (``files`` -- what
        actually gets tree-sitter'd for import statements); ``file_index`` (the resolution
        basename map) stays extension-agnostic regardless, since it needs to hold
        non-source-extension include targets too (BACK-491: ``.inc``/``.tcc``).
        """
        self.result = ProjectResolution(scan_root=scan_root)
        self._ruby_inventory_roots_seen = set()
        # Phases, split out for readability/complexity (BACK-566), same order and behavior
        # as before: (1) walk the tree into `files` + a basename index; (2) the project-wide
        # inputs extraction needs (PHP constants, Swift manifests, gemspec roots); (3) parse
        # every file once into its imports and its part of the indices; (4) resolve each
        # import to graph edges and add the convention-only Zeitwerk edges.
        files, file_index = self._discover_files(scan_root, supported_exts)
        inputs = self.prepare(files, scan_root)
        return self.resolve_entries(scan_root, files, file_index, self.index_files(files, inputs), inputs)

    @staticmethod
    def index_files(files: List[Path], inputs: 'ResolutionInputs') -> Dict[Path, 'FileEntry']:
        """Every file with an extractor parsed once, serially, into its ``FileEntry``."""
        entries: Dict[Path, FileEntry] = {}
        for file_path in files:
            extractor = get_extractor(file_path)
            if extractor:
                entries[file_path] = index_file(
                    file_path, extractor, extract_file(file_path, extractor, inputs.constant_index),
                    inputs.manifest_dirs)
        return entries

    def prepare(self, files: List[Path], scan_root: Path) -> 'ResolutionInputs':
        """The project-wide inputs per-file extraction and indexing read, built once before it.

        BACK-565: name -> ('literal', str) | ('absolute', str), the project-wide PHP
        framework-constant index (`define('ABSPATH', __DIR__ . '/')`) that `_concat_to_import`'s
        `ABSPATH . WPINC . '/version.php'`-shaped resolution looks up, built to a fixed point
        over `files` (real WordPress code chains constants through each other, and `files` is
        walk-ordered, not dependency-ordered). BACK-567: explicit-`path:` target dirs from every
        Package.swift, so each Swift file's module lookup can prefer an authoritative manifest
        mapping over the directory convention (see _swift_module_for); BACK-669 (swift-collections
        second corpus): every target NAME declared anywhere in a manifest, unioned into
        project_namespaces so a target reachable only through a computed `targets:` array is
        still known as in-tree for honest-decline purposes. BACK-669: extra bare-import search
        roots for a multi-package monorepo (RubyGems' *.gemspec + lib/), gated on the language
        being present. A manifest the walk cannot read joins the traversal failures.
        """
        if self.result.scan_root is None:
            self.result = ProjectResolution(scan_root=scan_root)
        constant_index, constant_ambiguous = self._build_constant_index(files)
        return ResolutionInputs(
            constant_index=constant_index,
            constants_ambiguous=len(constant_ambiguous),
            manifest_dirs=self._build_manifest_module_dirs(files),
            manifest_target_names=self._build_manifest_target_names(files),
            load_path_roots=self._build_load_path_roots(files, scan_root, on_error=self._record_manifest_failure),
        )

    def resolve_entries(self, scan_root: Path, files: List[Path], file_index: Dict[str, List[Path]],
                        entries: Dict[Path, 'FileEntry'], inputs: 'ResolutionInputs') -> ProjectResolution:
        """Resolve ``files`` (walk order) from their per-file ``entries`` (one per file with an
        extractor, made by ``index_file`` wherever the file was parsed: serially here, in pool
        workers for imports://) through the cascade, and add the Zeitwerk edges."""
        indices = self._build_resolution_indices(files, entries, inputs)
        self._graph = ImportGraph.from_imports(indices.all_imports)
        self.result.graph = self._graph
        self._resolve_edges(scan_root, file_index, indices)
        self._build_zeitwerk_edges(files, indices.zeitwerk_index)
        self._graph.traversal_failures = list(self.result.traversal_failures)
        return self.result

    def _discover_files(
        self, scan_root: Path, supported_exts: frozenset,
    ) -> Tuple[List[Path], Dict[str, List[Path]]]:
        """Walk `scan_root` into the parse corpus + a basename index.

        BACK-498: discover files the same way ImportsAdapter._build_graph does —
        since BACK-1580 literally the same walk (``discover_import_files``), not a
        raw rglob, which both scans build artifacts/vendor dirs it shouldn't and,
        on a repo where scan_root ends up far above the real project, times out —
        and build a basename -> [full paths] index alongside it. Package/namespace-resolved
        languages (Java, Kotlin, C#, PHP, Swift) need that index to resolve a
        dotted/qualified import to a file without their own tree walk; without
        it `resolve_import` silently fails for every such import and depends://
        reports "No dependents found" even though imports://?rank=fan-in sees
        the same edge (BACK-491 built this index for imports:// only).

        Records the file-count cap, the walk's losses and what it hid on ``self.result``.
        """
        files = service.discover(service.ScanScope(
            scan_root, supported_exts, cap=self._cap, focus=self._focus))
        self.record_discovery(files)
        return list(files.candidates), files.index

    def record_discovery(self, files: service.ImportFileSet) -> None:
        """The walk's census on the record: its losses, what it hid, and the cap's accounting
        (a caller that walked the root itself hands its file set here)."""
        self.result.traversal_failures = files.traversal_failures
        scope_hidden = hidden_entries_warning(files.hidden, files.analyzed)
        self.result.scope_hidden = dict(scope_hidden) if scope_hidden else None
        self.result.capped = files.capped
        self.result.scan_accounting = ScanBudget(self._cap).accounting(len(files.candidates), files.capped)
        if files.traversal_failures:
            # The combined source/target walk cannot certify the source census.
            self.result.scan_accounting = replace(self.result.scan_accounting, exact=False)

    def _build_resolution_indices(self, files: List[Path], entries: Dict[Path, 'FileEntry'],
                                  inputs: 'ResolutionInputs') -> _ResolutionIndices:
        """Merge every file's entry, in walk order, into the resolution indices.

        Produces everything edge resolution needs: the flat import list (→ ImportGraph), the
        package/namespace declaration sets (BACK-547/544/549: an unresolved dotted import is
        intra-project iff the project declares a matching package/namespace), the namespace
        index (BACK-554: namespace -> [declaring files], from every scanned file, so a
        zero-import leaf file's own declaration is indexed), the member index (BACK-547/557:
        (package, symbol) -> [declaring files]), the Zeitwerk index (BACK-557: constant path ->
        first declaring file) and the Swift module index (BACK-567: module -> [member files],
        whose keys also join project_namespaces as the in-tree module inventory). Also sets the
        autoload-coverage and PHP-constant counters and the parse failures.
        """
        self.result.constants_indexed = len(inputs.constant_index)
        self.result.constants_ambiguous = inputs.constants_ambiguous
        indices = _ResolutionIndices(
            all_imports=[], project_namespaces=set(inputs.manifest_target_names), namespace_index={},
            member_index={}, zeitwerk_index={}, module_index={}, load_path_roots=inputs.load_path_roots)
        for file_path in files:
            entry = entries.get(file_path)
            if entry is None:
                continue
            indices.all_imports.extend(entry.imports)
            if entry.autoloaded is not None:
                self.result.autoload_total += 1
                if entry.autoloaded:
                    self.result.autoload_with_imports += 1
            if entry.zeitwerk_path:
                # First declaration wins on a naming collision (two autoload roots producing
                # the same constant is an app misconfiguration, not something to guess between).
                indices.zeitwerk_index.setdefault(entry.zeitwerk_path, file_path)
            if entry.module_name:
                indices.module_index.setdefault(entry.module_name, []).append(file_path)
                indices.project_namespaces.add(entry.module_name)
            indices.project_namespaces.update(entry.declared)
            for ns in entry.namespace_keys:
                indices.namespace_index.setdefault(ns, []).append(file_path)
            for key in entry.member_keys:
                indices.member_index.setdefault(key, []).append(file_path)
            if entry.parse_failed:
                self.result.files_failed.append(str(file_path))  # BACK-1598
        return indices

    def _record_manifest_failure(self, error: OSError) -> None:
        """Resolution loss joins graph diagnostics without changing the source census."""
        failure = failure_of(error)
        self.result.traversal_failures += (failure,)

    @staticmethod
    def _build_load_path_roots(files: List[Path], scan_root: Path, *,
                               on_error: Optional[Callable[[OSError], None]] = None) -> List[Path]:
        """BACK-669 solidus second-corpus loop: every ``<dir>/lib`` sibling of a
        ``spec.load_path_manifest_glob`` match (RubyGems ``*.gemspec``) under
        ``scan_root`` — the real Bundler ``$LOAD_PATH`` roots a multi-gem
        monorepo (Rails Engine gems, each with its own gemspec) registers.

        Unlike Dart's ``package_manifest_filename`` (looked up by declared
        package *name*, BACK-621), a bare Ruby ``require 'a/b'`` carries no
        gem-name prefix to key a lookup by — every matching manifest's ``lib/``
        is added unconditionally as one more root :meth:`_resolve_path_target`
        tries, the same way the single project root already is. A single-gem
        project (one gemspec at the project root, e.g. Discourse) yields
        exactly one extra root whose ``lib/`` typically doesn't even exist —
        a no-op widening, not a behavior change, for the shape the original
        Ruby measurement was proven on.

        Globbed once from ``scan_root`` directly (not ``files``) because a
        ``.gemspec`` is never a ``source_extensions`` match for any language
        extractor, so it would never appear in the parsed file corpus.
        """
        glob = None
        for f in files:
            spec = getattr(get_extractor(f), 'spec', None)
            manifest_glob = getattr(spec, 'load_path_manifest_glob', None)
            if manifest_glob:
                glob = (manifest_glob, getattr(spec, 'load_path_lib_dirname', None))
                break
        if not glob or not glob[1] or not scan_root.is_dir():
            return []
        manifest_glob, lib_dirname = glob[0], str(glob[1])
        lib_dirs = (manifest.parent / lib_dirname
                    for manifest in load_path_manifests(scan_root, manifest_glob, on_error=on_error))
        return [lib_dir for lib_dir in lib_dirs if lib_dir.is_dir()]

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
            extractor: Any = get_extractor(f)
            pkg_dir = f.parent
            for name, path, _is_test in extractor.extract_manifest_targets(f):
                if not path:
                    continue  # default layout — the directory convention handles it
                dirs.append(((pkg_dir / path).resolve(), name))
        dirs.sort(key=lambda d: len(d[0].parts), reverse=True)
        return dirs

    @staticmethod
    def _build_manifest_target_names(files: List[Path]) -> Set[str]:
        """BACK-669 (swift-collections second corpus): every target NAME
        declared anywhere across every build manifest in the scan, via
        :meth:`~reveal.analyzers.imports.generic._GenericTreeSitterImportExtractor.extract_manifest_target_names`
        — a broader, position-independent sibling of
        :meth:`_build_manifest_module_dirs`. Fed into ``project_namespaces``
        (never into ``module_index``): a target declared via a computed
        ``targets:`` array (no literal ``Package(targets: [...])`` for
        :meth:`_build_manifest_module_dirs` to walk) still needs to be known
        as "a real in-tree module" so :meth:`_GenericTreeSitterImportExtractor.is_intra_project_import`
        can flag an import of it as reduced-confidence instead of silently
        dropping it when the directory-convention fallback can't find it
        (e.g. a target whose sanitized name doesn't match its own source
        directory's name)."""
        names: Set[str] = set()
        for f in files:
            spec = getattr(get_extractor(f), 'spec', None)
            manifest = getattr(spec, 'manifest_filename', None)
            if not manifest or f.name != manifest:
                continue
            extractor: Any = get_extractor(f)
            names.update(extractor.extract_manifest_target_names(f))
        return names

    @staticmethod
    def _swift_module_for(
        extractor: Any, file_path: Path, manifest_dirs: List[Tuple[Path, str]],
    ) -> Optional[str]:
        """The module a Swift file belongs to: an explicit-`path:` manifest
        target that contains it (longest prefix), else the directory convention
        (BACK-567)."""
        resolved = file_path.resolve()
        for abs_dir, module_name in manifest_dirs:
            if resolved == abs_dir or abs_dir in resolved.parents:
                return module_name
        return cast(Optional[str], extractor.module_for_file(file_path))

    def _resolve_edges(
        self, scan_root: Path, file_index: Dict[str, List[Path]],
        indices: _ResolutionIndices,
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
            # BACK-669: a multi-gem monorepo registers each gem's own lib/ on
            # $LOAD_PATH too (spec.load_path_manifest_glob) — a bare `require`
            # can target another gem's lib/ tree, not just the project root.
            spec = getattr(extractor, 'spec', None)
            if getattr(spec, 'load_path_manifest_glob', None) and indices.load_path_roots:
                extra_paths = extra_paths + indices.load_path_roots
            for stmt in imports:
                if stmt.is_type_checking:
                    continue
                self._resolve_statement_edges(
                    stmt, file_path, extractor, base_path, extra_paths,
                    file_index, indices)

    def _add_edge(self, stmt: ImportStatement, extractor: Any, file_path: Path, target: Path, via: str) -> None:
        """One edge of ``stmt``, tagged with the cascade stage that found it (``via``) and, when the
        importing language calls it its module layout, marked structural (BACK-2129). The statement
        records its first in-tree target (BACK-1193: any one proves it intra-project)."""
        self._graph.add_dependency(file_path, target, stmt.scope, via=via)
        service.mark_structural(self._graph, extractor, file_path, target)
        if stmt.resolved_path is None:
            stmt.resolved_path = target

    def _resolve_statement_edges(
        self, stmt: ImportStatement, file_path: Path, extractor: Any,
        base_path: Path, extra_paths: List[Path],
        file_index: Dict[str, List[Path]], indices: _ResolutionIndices,
    ) -> None:
        """Resolve a single import statement, walking the fallback cascade:
        direct resolution → namespace index (BACK-554) → member index
        (BACK-547/557) → honest-decline classification (BACK-547)."""
        added = self._add_direct_edges(
            stmt, file_path, extractor, base_path, extra_paths, file_index)
        spec = getattr(extractor, 'spec', None)
        if not added and indices.namespace_index and getattr(spec, 'resolve_namespaces', False):
            added = self._add_namespace_edges(stmt, file_path, extractor, indices) or added
        if not added and indices.member_index and (
                getattr(spec, 'member_symbol_fallback', False)
                or getattr(spec, 'container_member_fallback', False)
                or getattr(spec, 'namespaced_type_fallback', False)):
            added = self._add_member_edges(stmt, file_path, extractor, indices) or added
        if indices.module_index and getattr(spec, 'module_dir_convention', None):
            # Deliberately NOT gated on `not added` — see _add_module_edges.
            added = self._add_module_edges(stmt, file_path, extractor, indices) or added
        if not added:
            self._record_unresolved_if_intra(stmt, file_path, extractor, base_path, extra_paths, indices)

    def _add_direct_edges(
        self, stmt: ImportStatement, file_path: Path, extractor: Any,
        base_path: Path, extra_paths: List[Path],
        file_index: Dict[str, List[Path]],
    ) -> bool:
        """Stage 1: direct dotted-name resolution."""
        targets = service.resolve_targets(
            stmt, extractor, service.ResolutionContext(base_path, tuple(extra_paths), file_index))
        added = False
        via = VIA_CONSTANT if stmt.through_constant else VIA_DIRECT
        for resolved in targets:
            if resolved and resolved != file_path:
                self._add_edge(stmt, extractor, file_path, resolved, via)
                self._graph.resolved_paths[stmt.module_name] = resolved
                self.result.edge_statements[(file_path, resolved)] = stmt
                added = True
        return added

    def _add_namespace_edges(
        self, stmt: ImportStatement, file_path: Path, extractor: Any, indices: _ResolutionIndices,
    ) -> bool:
        """Stage 2 (BACK-554): the single-file dotted match above only
        catches a namespace that coincidentally names one matching file —
        the common case (a namespace declared across several files, or a
        file reachable only via a project-wide `global using`) needs the
        namespace index instead, fanning out to every declaring file
        (mirrors ImportsAdapter._resolve_dependencies, BACK-544)."""
        added = False
        for resolved in extractor.resolve_namespace_targets(stmt, indices.namespace_index):
            if resolved != file_path:
                self._add_edge(stmt, extractor, file_path, resolved, VIA_NAMESPACE)
                self.result.edge_statements[(file_path, resolved)] = stmt
                added = True
        return added

    def _add_member_edges(
        self, stmt: ImportStatement, file_path: Path, extractor: Any, indices: _ResolutionIndices,
    ) -> bool:
        """Stage 3: BACK-547 Kotlin measurement loop: `import a.b.foo` for a
        top-level fun/val/var — the direct dotted match above looked for
        `foo.kt` and failed, and BACK-551's enclosing-class peel can't help
        either (there is no enclosing type in the import path to peel down
        to). BACK-557 Scala measurement loop: same fallback also covers
        `import a.b.container.member` where `container` is a lowerCamelCase
        object BACK-551's peel refuses to reach. BACK-669 C# recall loop:
        same fallback also covers `using static Foo.Bar.Type;` / `using
        Alias = Foo.Bar.Type;`, whose target is a type one dotted component
        past any namespace the tree declares. Fall back to the
        content-scanned member index."""
        added = False
        for resolved in extractor.resolve_member_targets(stmt, indices.member_index):
            if resolved != file_path:
                self._add_edge(stmt, extractor, file_path, resolved, VIA_MEMBER)
                self.result.edge_statements[(file_path, resolved)] = stmt
                added = True
        return added

    def _add_module_edges(
        self, stmt: ImportStatement, file_path: Path, extractor: Any, indices: _ResolutionIndices,
    ) -> bool:
        """Stage 4 (BACK-567 Swift): `import Foo` names a whole SwiftPM
        target, not a file. Fan out to every file in module Foo via the
        path-derived module index — the same module→many-files shape C#'s
        namespace index uses. Deliberately called unconditionally by the
        caller (not gated on prior stages having added an edge): the direct
        bare-basename match resolves `import Foo` iff a UNIQUE `Foo.swift`
        exists (real case: ServerDrivenUI/ServerDrivenUI.swift), which is
        just one of the target's files — letting that pre-empt the fan-out
        would under-report the module to a single file. The fan-out is a
        superset (it includes that Foo.swift) and reverse_deps is
        set-keyed, so unioning is idempotent."""
        added = False
        for resolved in extractor.resolve_module_targets(stmt, indices.module_index):
            if resolved != file_path:
                self._add_edge(stmt, extractor, file_path, resolved, VIA_MODULE)
                self.result.edge_statements.setdefault((file_path, resolved), stmt)
                added = True
        return added

    def _record_unresolved_if_intra(
        self, stmt: ImportStatement, file_path: Path, extractor: Any,
        base_path: Path, extra_paths: List[Path], indices: _ResolutionIndices,
    ) -> None:
        """Stage 5 (BACK-547 honest-decline): an extracted import that
        produced no edge is only a false-negative risk if it points
        intra-project. External (stdlib/dep) imports correctly have no
        in-tree edge; None means the extractor can't tell, and we
        conservatively don't count it (never cry wolf)."""
        if isinstance(extractor, RubyImportExtractor):
            verdict, inventory = extractor._classify_with_inventory(stmt, base_path)
            # Replay each cached build once, retaining distinct unlocated events within it.
            if inventory is not None and inventory.root not in self._ruby_inventory_roots_seen:
                self._ruby_inventory_roots_seen.add(inventory.root)
                self.result.traversal_failures += inventory.traversal_failures
        else:
            verdict = extractor.is_intra_project_import(
                stmt, base_path, search_paths=extra_paths,
                project_namespaces=indices.project_namespaces)
        if verdict is True:
            self.result.unresolved_intra += 1
            if len(self.result.unresolved_examples) < 5:
                self.result.unresolved_examples.append((file_path, stmt))
        elif verdict is None and not depends_intra_project_classification_supported(
            extractor.language_name
        ):
            # BACK-1093: this extractor can never return True/False for any
            # import shape (always None) — this unresolved import is
            # invisible to unresolved_intra not because it was verified
            # external, but because the language has no honest-decline
            # signal at all. Disclosed once per language by the caller,
            # not per-import (that would be per-file noise, same reasoning
            # as unresolved_examples' 5-item cap).
            self.result.unclassifiable_languages.add(extractor.language_name)

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
            extractor: Any = get_extractor(file_path)
            if extractor is None:
                continue
            spec = getattr(extractor, 'spec', None)
            if not getattr(spec, 'zeitwerk_convention', False):
                continue
            for line_no, const_path in extractor.extract_constant_references(file_path):
                target = zeitwerk_index.get(const_path)
                if target is None or target == file_path:
                    continue
                self._graph.add_dependency(file_path, target, via=VIA_CONVENTION)
                self.result.zeitwerk_edges += 1
                if (file_path, target) not in self.result.edge_statements:
                    # No real statement backs this edge — synthesize one
                    # so file-dependents display still shows a module
                    # name and line rather than falling through to the
                    # generic 'unknown'-type dependent entry.
                    self.result.edge_statements[(file_path, target)] = ImportStatement(
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
        before the expensive one" shape as `is_noise_dir`.
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
                text = file_path.read_text(errors='ignore', encoding='utf-8')
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
                defining: Any = get_extractor(file_path)
                if not defining:
                    continue
                for name, value in defining.extract_constant_defines(file_path, index):
                    candidates.setdefault(name, set()).add(value)
            new_index: Dict[str, Tuple[str, str]] = {}
            ambiguous = set()
            for name, values in candidates.items():
                if len(values) == 1:
                    new_index[name] = next(iter(values))
                else:
                    ambiguous.add(name)
            if new_index == index:
                return new_index, ambiguous
            index = new_index
        return index, ambiguous


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
