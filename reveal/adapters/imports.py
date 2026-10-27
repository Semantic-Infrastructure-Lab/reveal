"""imports:// adapter - Import graph analysis.

Analyze import relationships in codebases:
- List all imports in a directory
- Detect unused imports (?unused)
- Find circular dependencies (?circular)
- Validate layer violations (?violations)

Usage:
    reveal imports://src                     # All imports
    reveal 'imports://src?unused'            # Find unused
    reveal 'imports://src?circular'          # Find cycles
"""

import difflib
import hashlib
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, Sequence, Tuple, cast
from reveal.reveal_types import CONTRACT_VERSION, PathFailure, WarningEntry

from .base import ResourceAdapter, register_adapter, register_renderer
from .help_data import load_help_data
from ..core import disk_cache
from ..utils.formatting import cwd_path
from ..utils import print_json_result
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.types import (
    LAZY_EXCLUDE, LAZY_INCLUDE, LAZY_MODES, ImportAnalysis, ImportExtraction,
)
from ..analyzers.imports.classify import classify_import, local_package_names, package_table
from ..analyzers.imports.unused import describe_unused
from ..conventions import conventions_for_path, family_for_path, same_package_families
from ..analyzers.imports.base import build_project_namespaces
from ..analyzers.imports.layers import load_layer_config
from ..utils.query import parse_query_params
from ..utils.query_parser import CliBinding, ParamSpec, QueryParams, ResourceSpec
from ..utils.query_binding import boolean_value
from ..analyzers.imports import service as import_analysis
from ..analyzers.imports import resolution
from ..analyzers.imports.file_index import resolution_fingerprint
from ..registry import get_code_extensions
from ..utils.parallel import pool_worker_count, submit_each, worker_lost_warning as _worker_lost_warning
from ..utils.path_utils import hidden_entries_warning, is_test_path, to_posix, to_relative_display
from ..utils.query_control import ScanBudget
from ..utils.request_cache import in_host_request, register_request_cache, register_validated_cache
from ..utils.results import ResultBuilder, note_truncation
from ..utils.warning_render import meta_warning_lines

# Disk-cache namespace for this adapter's resolved import graph (BACK-834).
# Mirrors rules/imports/I002.py's own import-graph disk cache (_tree_fingerprint
# / _IMPORT_GRAPH_NAMESPACE) — same fingerprint recipe (path + mtime_ns + size
# per source and indexed target file), but this adapter builds a graph rooted at whatever
# `path` argument the caller gave it (imports://<path>, pack --architecture,
# pack --focus), not I002's resolved *project* root, so it gets its own
# namespace rather than sharing I002's cache entries.
_ADAPTER_IMPORT_GRAPH_NAMESPACE = "adapter_import_graph"

def _candidate_set_fingerprint(candidates: List[Path],
                               file_index: Optional[Dict[str, List[Path]]] = None, *, root: Path,
                               traversal_failures: Sequence[PathFailure] = ()) -> Optional[str]:
    """Shared root/source/target fingerprint; preserve the private source-only call shape."""
    return resolution_fingerprint(candidates, {} if file_index is None else file_index, excluded_root=disk_cache.cache_root(),
                                  root=root, traversal_failures=traversal_failures)


def _graph_cache_key(candidates: List[Path], file_index: Dict[str, List[Path]], root: Path,
                     traversal_failures: Sequence[PathFailure], cap: Optional[int],
                     parsed: Optional[frozenset] = None) -> Optional[str]:
    """The whole-graph cache key: the resolution fingerprint of the scan root, plus the build's
    identity (the file cap the walk ran under, the extensions it parsed: every supported one unless
    a caller narrowed them, ``parse_extensions``). None: not cacheable."""
    fingerprint = _candidate_set_fingerprint(candidates, file_index, root=root,
                                             traversal_failures=traversal_failures)
    if fingerprint is None:
        return None
    exts = parsed if parsed is not None else get_all_extensions()
    identity = f'{fingerprint}|cap={cap}|exts={",".join(sorted(exts))}'
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


# BACK-1054 (the BACK-2109 pattern): inside a host request (MCP, reveal.api) the resolved graph of
# a scan root is kept across requests while the tree stamp of that root is unchanged
# (register_validated_cache), so a repeated per-file ?importers= answers without a rebuild when
# the disk cache is off or cold. Keyed by the root alone, as resolved; the value holds at most
# _GRAPH_MEMO_VARIANTS builds, each under the cache key it was built for (which already carries
# the source set, targets and file cap) and the --exclude/gitignore scope the walk ran under,
# which the tree stamp cannot see. A build with a gitignore-off scope lives for its request only
# (the BACK-2118 rule). &scope, &tests and &lazy are applied at presentation: never a variant.
_GRAPH_MEMO: 'OrderedDict[str, List[Tuple[Tuple[str, Any, bool], ImportAnalysis]]]' = OrderedDict()
_GRAPH_MEMO_ROOTS = 4
_GRAPH_MEMO_VARIANTS = 2


def _evict_graph_root(root: str) -> None:
    _GRAPH_MEMO.pop(root, None)


def _drop_request_local_graphs() -> None:
    for root, builds in tuple(_GRAPH_MEMO.items()):
        kept = [build for build in builds if build[0][2]]
        if kept:
            _GRAPH_MEMO[root] = kept
        else:
            del _GRAPH_MEMO[root]


register_request_cache(__name__ + '.graph_request_local', _drop_request_local_graphs)
register_validated_cache(__name__ + '.graph', _GRAPH_MEMO, _evict_graph_root)


def _memo_variant(key: str) -> Tuple[str, Any, bool]:
    from ..utils.exclusions import active_exclusions
    from ..utils.gitignore import gitignore_enabled
    return key, active_exclusions(), gitignore_enabled()


def _recall_graph(root: Path, key: str) -> Optional[ImportAnalysis]:
    """The build this host request may reuse for *root* and *key*; None outside a request."""
    if not in_host_request():
        return None
    variant = _memo_variant(key)
    for built_for, analysis in _GRAPH_MEMO.get(str(root), []):
        if built_for == variant:
            _GRAPH_MEMO.move_to_end(str(root))
            return analysis
    return None


def _remember_graph(root: Path, key: str, analysis: ImportAnalysis) -> None:
    """Keep a cacheable build for the rest of this host request and the next ones (validated)."""
    if not in_host_request() or not analysis.cacheable:
        return
    variant = _memo_variant(key)
    builds = [build for build in _GRAPH_MEMO.get(str(root), []) if build[0] != variant]
    _GRAPH_MEMO[str(root)] = [*builds, (variant, analysis)][-_GRAPH_MEMO_VARIANTS:]
    _GRAPH_MEMO.move_to_end(str(root))
    if len(_GRAPH_MEMO) > _GRAPH_MEMO_ROOTS:
        _GRAPH_MEMO.popitem(last=False)


def _cached_graph(root: Path, key: Optional[str]) -> Optional[ImportAnalysis]:
    """The stored build for *key*: the host-request memo first, then the disk layer (a disk hit
    joins the memo). A record from before the cascade (no ``resolution``) is a miss."""
    if key is None:
        return None
    cached = _recall_graph(root, key)
    if cached is None:
        cached = disk_cache.get(_ADAPTER_IMPORT_GRAPH_NAMESPACE, key)
    if not isinstance(cached, ImportAnalysis) or cached.resolution is None:
        return None
    _remember_graph(root, key, cached)
    return cached


def _discovery_incomplete(result: Dict[str, Any]) -> bool:
    """Whether the available import graph lost required directory enumeration."""
    return any(w.get('type') == 'analysis_incomplete' for w in result.get('meta', {}).get('warnings', []))


def _module_label(path: str) -> str:
    p = Path(path)
    return '/'.join(p.parts[-2:]) if p.name == '__init__.py' else p.name


def _unused_not_checked(scanned_files) -> Dict[str, int]:
    from ..analyzers.imports.base import extension_detects_unused
    tally: Dict[str, int] = {}
    for fp in scanned_files:
        if not extension_detects_unused(fp.suffix):
            ext = fp.suffix.lower()
            tally[ext] = tally.get(ext, 0) + 1
    return dict(sorted(tally.items()))


def unused_not_checked_line(not_checked: Dict[str, int]) -> str:
    """'Unused imports not checked for X' disclosure (empty if none) -- BACK-1398."""
    if not not_checked:
        return ''
    exts = ', '.join(f'{ext} ({n} file{"s" if n != 1 else ""})' for ext, n in not_checked.items())
    return f"⚠ Unused imports not checked — no unused-import detection for: {exts}"


def coverage_warning_line(unsupported: Dict[str, int]) -> str:
    """One-line 'N files skipped, no import support for X' warning (empty if none).

    Shared by imports:// and every downstream command (architecture, overview)
    that builds an ImportGraph and needs to disclose the same gap (BACK-518
    part 2) instead of silently presenting a partial graph as the whole tree.
    """
    if not unsupported:
        return ''
    skipped_total = sum(unsupported.values())
    exts = ', '.join(f"{ext} ({n})" for ext, n in sorted(unsupported.items()))
    return f"⚠ {skipped_total} code file(s) not analyzed — no import support for: {exts}"


# BACK-1245: cheap, conservative, manifest-only detection of a convention-
# autoloading framework regime. Rails/Django/Laravel load most application
# code by naming convention, not require/import/use -- for these, the
# explicit import graph these adapters build is structurally thin (near-
# meaningless, not just "somewhat approximate"), but the only prior
# disclosure was a generic one-liner ("dynamically loaded files may appear
# as entry points") that reads as a minor edge case regardless of which
# regime is in play. False negatives here (a framework not in this table)
# are safe -- callers just keep seeing the generic caveat; a false positive
# would not be, so detection intentionally requires an unambiguous manifest
# marker, not a guess from file extensions alone.
_AUTOLOAD_REGIMES: Tuple[Tuple[str, str, str], ...] = (
    # (manifest filename, content substring to require (empty = presence-only), framework label)
    ('Gemfile', "gem 'rails'", 'Ruby on Rails'),
    ('Gemfile', 'gem "rails"', 'Ruby on Rails'),
    ('manage.py', '', 'Django'),
    ('artisan', '', 'Laravel'),
)


_AUTOLOAD_REGIME_MAX_WALK_UP = 6


def worker_lost_warning(lost_files: List[str], base: Optional[Path] = None) -> Optional[WarningEntry]:
    """One meta warning for the files a dead pool worker took down before they were
    parsed (BACK-1753): not a parse error, and a file with no import extractor loses
    its structure the same way (BACK-1752)."""
    return cast(Optional[WarningEntry], _worker_lost_warning(
        lost_files, "their imports and structure are missing, so results can under-report", base))


def parse_failure_warning(failed_files: List[str], base: Optional[Path] = None) -> Optional[WarningEntry]:
    """One meta warning for the files tree-sitter parsed with errors (BACK-1598).

    The per-file extractor only sets ``parse_failed``; every command that builds
    an import graph discloses the set once, through this, rather than one log
    line per file per extraction pass (364 stderr lines on a cold `reveal
    overview` of Redis src/, none on a warm one, and never in the result).
    """
    if not failed_files:
        return None
    shown = [to_relative_display(f, base) if base else to_posix(f) for f in sorted(failed_files)[:5]]
    more = f" and {len(failed_files) - len(shown)} more" if len(failed_files) > len(shown) else ''
    return {
        'type': 'partial_parse',
        'count': len(failed_files),
        'files': shown,
        'message': (
            f"{len(failed_files)} file(s) parsed with errors -- their imports may be incomplete, "
            f"so import-graph results can under-report: {', '.join(shown)}{more}"
        ),
    }


def file_loss_warnings(analysis: ImportAnalysis, base: Optional[Path] = None, *,
                       spell: Optional[Callable[[Optional[str]], Optional[str]]] = None) -> List[WarningEntry]:
    """The per-file facts of one import build, each under its own cause (BACK-2190).

    ``files_failed`` holds three different things, and the user's next step differs: a file
    tree-sitter recovered with ERROR nodes (``partial_parse``: its recovered imports are edges), a
    file never parsed because it could not be read (``analysis_failed``, named by the OSError type:
    no tree, its imports are missing) and a file a dead pool worker took (``worker_lost``).
    ``spell`` names each file as the answer does (imports' ``_path_display``) instead of ``base``."""
    from .ast.analysis import analysis_skipped_warning
    name = _spelled(spell)
    if spell is not None:
        base = None
    lost = set(analysis.files_lost)
    partial: List[str] = []
    unread: List[Tuple[str, str]] = []
    for path in analysis.files_failed:
        if path in lost:
            continue
        extraction = analysis.extractions.get(path)
        parse = (extraction.diagnostics.get('parse') or {}) if extraction is not None else {}
        read_error = extraction.read_error if extraction is not None else None
        # Only a file whose tree was never built is unreadable (status 'unavailable', or an OSError);
        # a failed file with no such record is a parse failure, as it was before BACK-2190.
        if read_error or parse.get('status') == 'unavailable':
            unread.append((name(path), f'{read_error}: {parse.get("reason", "")}' if read_error
                           else str(parse.get('reason') or 'not parsed')))
        else:
            partial.append(name(path))
    warnings = [parse_failure_warning(partial, base), worker_lost_warning([name(p) for p in lost], base),
                analysis_skipped_warning(unread, base, 'analysis is incomplete; its imports are missing from the '
                                                       'import graph')]
    return [w for w in warnings if w]


def _spelled(spell: Optional[Callable[[Optional[str]], Optional[str]]]) -> Callable[[Any], str]:
    """``str`` of a path, or the answer's spelling of it when the caller passes one."""
    if spell is None:
        return str
    return lambda path: spell(str(path)) or str(path)


def detect_autoload_regime(path: Path) -> Optional[Dict[str, str]]:
    """Return {'framework': ..., 'evidence': ...} if `path` -- or an ancestor,
    up to _AUTOLOAD_REGIME_MAX_WALK_UP levels up -- looks like a
    convention-autoloading project's root; None otherwise. See
    _AUTOLOAD_REGIMES for what's covered.

    Walks upward because a real invocation typically targets a subdirectory
    (`imports://app/models`, `architecture://src/entities`), not the project
    root where Gemfile/manage.py/artisan actually live -- checking only the
    exact queried path would silently miss the common case (confirmed: the
    due-diligence recipe this was filed against runs adapters against
    subdirectories routinely). Crossing into an unrelated enclosing project
    is possible but low-cost (an extra, still-true disclosure line) compared
    to the silent miss this fixes.
    """
    try:
        base = (path if path.is_dir() else path.parent).resolve()
    except OSError:
        return None
    seen_frameworks: set = set()
    current = base
    for _ in range(_AUTOLOAD_REGIME_MAX_WALK_UP):
        for filename, needle, framework in _AUTOLOAD_REGIMES:
            if framework in seen_frameworks:
                continue
            candidate = current / filename
            if not candidate.is_file():
                continue
            if not needle:
                seen_frameworks.add(framework)
                continue
            try:
                if needle in candidate.read_text(errors='ignore', encoding='utf-8'):
                    seen_frameworks.add(framework)
            except OSError:
                continue
        if seen_frameworks:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    if not seen_frameworks:
        return None
    framework = sorted(seen_frameworks)[0]
    evidence = next(f"{fn} ({framework.split()[-1].lower()} marker)" for fn, _, fw in _AUTOLOAD_REGIMES if fw == framework)
    return {'framework': framework, 'evidence': evidence}


def autoload_regime_warning(regime: Optional[Dict[str, str]]) -> str:
    """Strong, framework-named disclosure line for when detect_autoload_regime()
    finds a hit -- distinct from the generic 'dynamically loaded files may
    appear as entry points' caveat this is meant to sit alongside, not
    replace (BACK-1245: that caveat reads as a minor edge case even on a
    codebase where it describes almost the entire application).
    """
    if not regime:
        return ''
    return (
        f"⚠ {regime['framework']} detected ({regime['evidence']}) — this framework "
        "loads most application code by naming convention, not require/import. "
        "fan-in/fan-out/circular/entry-point signals below reflect only the small "
        "explicit import graph, not real usage; treat them as unreliable for this "
        "codebase, not merely approximate."
    )


def _lazy_value(value: Any) -> str:
    if not isinstance(value, str):  # a bare `&lazy` parses as True
        raise TypeError(value)
    return value


# BACK-2077: which edges an edge-derived answer counts, by the scope of the imports behind
# each edge. No default here: every view has its own (cycles leave lazy edges out).
_LAZY = ParamSpec(
    'lazy', 'string',
    'Function-level (lazy) import edges: include them, exclude them (load-time edges only: '
    'the architecture view) or show only them. Default: ?circular and has_cycles exclude, '
    'every other view includes. Python, JavaScript, TypeScript and TSX record import scope; '
    'other languages\' edges count as load-time under every value, and the printed rule names them',
    None, _lazy_value,
    examples=('imports://src?rank=fan-in&lazy=exclude', 'imports://src?circular&lazy=include'),
    choices=LAZY_MODES,
)

def _choice_value(value: Any) -> str:
    if not isinstance(value, str):  # a bare `&scope` parses as True
        raise TypeError(value)
    return value


def _max_files_value(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError(value)
    return int(value)


def _importers_value(value: Any) -> Any:
    """A bare ``?importers`` (True) asks for every module under the path; a value names one file."""
    if value is True:
        return True
    if not isinstance(value, str) or not value:
        raise TypeError(value)
    return value


# BACK-1054 (slice S2 of folding depends://, deps:// and calls?modules into imports://): where an
# answer is resolved, which rows it shows and which importers count. Each is read where it is
# applied; none of them enters a cache key (the root does).
SCOPE_ROOT, SCOPE_PATH = 'root', 'path'
_SCOPE = ParamSpec(
    'scope', 'string',
    'root (default): resolve at the project root the climb finds (?root=, .reveal.yaml root: true, '
    'package marker, VCS root, else the requested directory) and show rows under the requested path, '
    'counting importers from anywhere under the root. path: the requested path is the scan root, '
    'as imports:// resolved before (architecture, overview, pack and diff pass it)',
    SCOPE_ROOT, _choice_value,
    examples=('imports://src?rank=fan-in&scope=path',), choices=(SCOPE_ROOT, SCOPE_PATH),
)
_TESTS = ParamSpec(
    'tests', 'string',
    'Importers under a test path (path_utils.is_test_path: a tests/ or test/ directory, '
    'test_*.py, *_test.go, *.spec.ts, ...): include them (default) or exclude them from every count',
    'include', _choice_value,
    examples=('imports://src?rank=fan-in&tests=exclude',), choices=('include', 'exclude'),
)
_ROOT = ParamSpec(
    'root', 'string',
    'Pin the scan root to DIR (beats .reveal.yaml, package and VCS markers): resolved against cwd, '
    'must be an existing directory containing the path, not a filesystem/home/system root; a refused '
    'value says why and the climb decides. Ignored with scope=path',
    None, _choice_value, examples=('imports://src/app.py?importers&root=.',),
)
_MAX_FILES = ParamSpec(
    'max_files', 'integer',
    'Source files the walk may keep (default 20000); a capped walk is disclosed in metadata.scan_budget '
    'and as a warning, never silently partial',
    20000, _max_files_value, examples=('imports://.?importers&max_files=50000',), minimum=1,
)
_IMPORTERS = ParamSpec(
    'importers', 'string',
    'Who imports what: bare (or on a directory) lists every module under the path with its sorted '
    'importers; =FILE (relative to the path) or a file path lists that file\'s importers with the import '
    'line, scope and the cascade stage (via) of each edge',
    None, _importers_value, names='file',
    examples=('imports://src?importers', 'imports://src?importers=utils.py', 'imports://src/utils.py?importers'),
)
_REQUEST_SPECS = (_LAZY, _SCOPE, _TESTS, _ROOT, _MAX_FILES, _IMPORTERS)

# Component cohesion (internal / (internal + outgoing) imports) is declined, not computed, for a component whose
# files are mostly in a language where one package/module sees its own files with no import (BACK-1428).
COHESION_DECLINED_REASON = 'same-package visibility'
COHESION_DECLINED_RULE = (
    'cohesion n/a (' + COHESION_DECLINED_REASON + '): a component with more than half its files in ' + ', '.join(same_package_families())
    + ' is not scored, because files of one package or module use each other without an import, so internal imports '
    'would read ~0 whatever the structure; other languages keep their number')


def _component_cohesion(internal: int, total: int, files) -> Optional[float]:
    """internal / (internal + outgoing), or None where the component's language makes it meaningless."""
    if _cohesion_declined(files):
        return None
    return internal / total if total > 0 else 0.0


def _cohesion_fields(cohesion: Optional[float]) -> Dict[str, Any]:
    """The row's cohesion, rounded, or its decline: ``cohesion: None`` and ``cohesion_reason``."""
    if cohesion is None:
        return {'cohesion': None, 'cohesion_reason': COHESION_DECLINED_REASON}
    return {'cohesion': round(cohesion, 3)}


def _cohesion_declined(files) -> bool:
    """Whether a component's files are mostly (strictly more than half) in a same-package-visibility language."""
    same = sum(1 for f in files if conventions_for_path(str(f)).same_package_visibility)
    return 2 * same > len(files)

# BACK-2194: the Graphviz module view, the replacement for calls ?modules &format=dot. URI-only, as
# on calls:// (dot has no --format spelling); it draws the edges ?importers lists for a directory.
_FORMAT = ParamSpec(
    'format', 'string',
    'URI output override for ?importers on a directory: dot draws one importer -> module edge per '
    'listed importer as Graphviz (pipe to dot -Tsvg); text and json follow --format',
    None, _choice_value, examples=('imports://src?importers&scope=path&format=dot',),
    choices=('text', 'json', 'dot'), role='presentation',
)


def _flag(name: str, description: str) -> ParamSpec:
    return ParamSpec(name, 'boolean', description, False, boolean_value, (f'imports://src?{name}',),
                     role='operation', cli=CliBinding((f'--{name}',), action='store_true'))


def _top_value(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError(value)
    return int(value)


# The answer types --verbose expands (the renderers that take it).
_VERBOSE_VIEWS = frozenset({'unused_imports', 'circular_dependencies', 'layer_violations',
                           'module_importers', 'importer_summary', 'external_packages'})


# The declaration the `reveal imports` subcommand and the declared URI route bind (BACK-1054, D6):
# every parameter imports:// reads. The views read presence for the flags, as the URI always did.
PARAM_SPECS: Tuple[ParamSpec, ...] = (
    _flag('unused', 'Find unused imports'),
    _flag('circular', 'Detect circular dependencies (load-time edges unless &lazy says otherwise)'),
    _flag('violations', 'Check layer violations (requires .reveal.yaml layers)'),
    ParamSpec('rank', 'string', 'Rank files by fan-in (one value: fan-in)', None, _choice_value,
              ('imports://src?rank=fan-in',), choices=('fan-in',), role='operation',
              cli=CliBinding(('--rank',), metavar='fan-in')),
    ParamSpec('top', 'integer', 'Limit ?rank rows (default: all)', None, _top_value,
              ('imports://src?rank=fan-in&top=20',), minimum=0, role='analysis',  # the adapter cuts the rows
              cli=CliBinding(('--top',), metavar='N')),
    _flag('entrypoints', 'Files with fan-in 0 (entry points, scripts or dead code)'),
    _flag('components', 'Score each directory as a component'),
    _flag('external', 'Package table: unresolved (third-party or unresolved-local) and stdlib packages by use'),
    ParamSpec('verbose', 'boolean', 'Show everything instead of a summary (same as --verbose)', False,
              boolean_value, ('imports://src?circular&verbose',), role='presentation'),
    *(ParamSpec(spec.name, spec.type, spec.description, spec.default, spec.convert, spec.examples,
                minimum=spec.minimum, choices=spec.choices, role='analysis',
                cli=CliBinding((f'--{spec.name.replace("_", "-")}',), dest=spec.name,
                               metavar=spec.name.upper()))
      for spec in _REQUEST_SPECS if spec is not _IMPORTERS),
    ParamSpec(_IMPORTERS.name, _IMPORTERS.type, _IMPORTERS.description, None, _IMPORTERS.convert,
              _IMPORTERS.examples, role='operation', names=_IMPORTERS.names,
              cli=CliBinding(('--importers',), nargs='?', metavar='FILE')),
    _FORMAT,
)
_FLAG_NAMES = frozenset(spec.name for spec in PARAM_SPECS if spec.type == 'boolean')

_SCHEMA_QUERY_PARAMS = {
    'unused': {
        'type': 'flag',
        'description': 'Find unused imports in codebase',
        'examples': ['imports://src?unused']
    },
    'circular': {
        'type': 'flag',
        'description': 'Detect circular dependencies',
        'examples': ['imports://src?circular']
    },
    'violations': {
        'type': 'flag',
        'description': 'Check for layer violations (requires config)',
        'examples': ['imports://src?violations']
    },
    'rank': {
        'type': 'enum',
        'values': ['fan-in'],
        'description': 'Rank files by structural metric. fan-in: count of files that import each file (higher = more central; 0 = entry point or dead code)',
        'examples': ['imports://src?rank=fan-in', 'imports://src?rank=fan-in&top=20']
    },
    'top': {
        'type': 'integer',
        'description': 'Limit results for ?rank (default: all files)',
        'examples': ['imports://src?rank=fan-in&top=20']
    },
    'entrypoints': {
        'type': 'flag',
        'description': 'List files with fan-in=0 — nothing imports them (entry points, scripts, or dead code); sorted by fan-out descending',
        'examples': ['imports://src?entrypoints']
    },
    'components': {
        'type': 'flag',
        'description': 'Score each directory as a component: cohesion (internal/outgoing imports; null/n/a for a component mostly in Go, Java, Kotlin, C#, Scala or Swift, with cohesion_rule saying why), coupling (incoming), top bridge file',
        'examples': ['imports://src?components']
    },
    'external': {
        'type': 'flag',
        'description': ('Package table (the deps:// dashboard\'s, as JSON): every import of the files under the path '
                        'classified on resolution truth first -- resolved in the tree (internal), stdlib (a '
                        'language rule or marker, never Python\'s list for another language) or unresolved '
                        '(third-party or an unresolved local) -- with uses per package, the languages importing '
                        'each unresolved package, and import statements per file. &tests=exclude drops test files'),
        'examples': ['imports://src?external', 'imports://src?external&scope=path'],
    },
    'verbose': {
        'type': 'flag',
        'description': 'Show everything instead of a summary: every file in a cycle group plus its cycle edges, all unused imports, all violations, every package. Same as the CLI --verbose',
        'examples': ['imports://src?circular&verbose']
    },
    'lazy': _LAZY.schema(),
    'importers': _IMPORTERS.schema(),
    'scope': _SCOPE.schema(),
    'tests': _TESTS.schema(),
    'root': _ROOT.schema(),
    'max_files': _MAX_FILES.schema(),
    'format': _FORMAT.schema(),
}

# BACK-2077: the counting rule every edge-derived answer carries (service.edge_rule).
_EDGE_RULE_SCHEMA = {
    'type': 'object',
    'properties': {
        'lazy': {'type': 'string', 'enum': list(LAZY_MODES)},
        'lazy_default': {'type': 'boolean'},
        'type_checking': {'type': 'string', 'const': 'excluded'},
        'tests': {'type': 'string', 'enum': ['included', 'importers_not_counted']},
        'scope': {'type': 'string', 'enum': ['scanned_path', 'scan_root']},
        'unclassified_edges': {'type': 'integer'},
        'unclassified_languages': {'type': 'array', 'items': {'type': 'string'}},
        # BACK-1054: where the answer was resolved and which rows it shows.
        'root': {'type': 'string', 'description': 'scan root, relative to the requested path'},
        'root_source': {'type': 'string', 'enum': list(resolution.ROOT_SOURCES)},
        'scope_param': {'type': 'string', 'enum': [SCOPE_ROOT, SCOPE_PATH]},
        'tests_param': {'type': 'string', 'enum': ['include', 'exclude']},
        'via': {'type': 'object', 'description': 'counted edges by the cascade stage that found them',
                'additionalProperties': {'type': 'integer'}},
        'ungated_languages': {'type': 'array', 'items': {'type': 'string'}},
        'ungated_edges': {'type': 'integer'},
        'outside_root_edges': {'type': 'integer', 'description': 'edges whose target lies outside the scan root, not counted'},
        'text': {'type': 'string'},
    },
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'imports',
        'description': 'Full import listing for all files in the codebase (default output)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'imports'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'files': {'type': 'object'},
                'metadata': {
                    'type': 'object',
                    'properties': {
                        'total_files': {'type': 'integer'},
                        'total_imports': {'type': 'integer'},
                        'has_cycles': {'type': 'boolean'},
                        'cycles_lazy': {'type': 'string', 'enum': list(LAZY_MODES)},
                    }
                },
                'edge_rule': _EDGE_RULE_SCHEMA,
            }
        }
    },
    {
        'type': 'unused_imports',
        'description': 'List of unused imports with file locations',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'unused_imports'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'count': {'type': 'integer'},
                'unused': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'line': {'type': 'integer'},
                            'module': {'type': 'string'}
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'circular_dependencies',
        'description': 'Detected circular import cycles',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'circular_dependencies'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'count': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'cycles': {
                    'type': 'array',
                    'items': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    }
                }
            }
        }
    },
    {
        'type': 'layer_violations',
        'description': 'Architectural layer violations',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'layer_violations'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'count': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'violations': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'from_file': {'type': 'string'},
                            'to_file': {'type': 'string'},
                            'layer': {'type': 'string'},
                            'reason': {'type': 'string'}
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'fan_in_ranking',
        'description': 'Files ranked by fan-in (importer count) — high fan-in = core abstractions; zero fan-in = entry points or dead code',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'fan_in_ranking'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'fan_in': {'type': 'integer'},
                            'fan_out': {'type': 'integer'},
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'components',
        'description': 'Per-directory cohesion and coupling scores — validates directory-as-component hypothesis',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'components'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'cohesion_rule': {'type': 'string', 'description': 'Present when any component declined its cohesion: why (BACK-1428)'},
                'components': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'component': {'type': 'string'},
                            'files': {'type': 'integer'},
                            'internal': {'type': 'integer'},
                            'outgoing': {'type': 'integer'},
                            'incoming': {'type': 'integer'},
                            'cohesion': {'type': ['number', 'null'], 'description': 'null = declined, see cohesion_reason (more than half the files are in a same-package-visibility language); declined components sort after measured ones'},
                            'cohesion_reason': {'type': 'string', 'description': 'Only on a declined component'},
                            'top_bridge': {'type': ['string', 'null']},
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'entrypoints',
        'description': 'Files with fan-in=0 — nothing imports them (entry points, scripts, or dead code)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'entrypoints'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total_scanned': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'fan_out': {'type': 'integer'},
                        }
                    }
                }
            }
        }
    }
]

_SCHEMA_OUTPUT_TYPES += [
    {
        'type': 'module_importers',
        'description': 'The files that import one file (?importers on a file, or ?importers=FILE)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'module_importers'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'target': {'type': 'string'},
                'count': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'importers': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'}, 'line': {'type': 'integer'}, 'module': {'type': 'string'},
                            'names': {'type': 'array', 'items': {'type': 'string'}}, 'type': {'type': 'string'},
                            'is_relative': {'type': 'boolean'}, 'alias': {'type': ['string', 'null']},
                            'scope': {'type': ['array', 'null'], 'items': {'type': 'string'}},
                            'via': {'type': ['array', 'null'], 'items': {'type': 'string'}},
                        },
                    },
                },
            },
        },
    },
    {
        'type': 'importer_summary',
        'description': 'Every module under the path with its sorted importers (?importers on a directory)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'importer_summary'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'}, 'fan_in': {'type': 'integer'},
                            'importers': {'type': 'array', 'items': {'type': 'string'}},
                        },
                    },
                },
            },
        },
    },
]

_SCHEMA_OUTPUT_TYPES += [
    {
        'type': 'external_packages',
        'description': 'Unresolved and stdlib packages by use (?external; deps:// printed it in text only)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'external_packages'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total_imports': {'type': 'integer', 'description': 'import statements counted'},
                'total_files': {'type': 'integer', 'description': 'files with at least one import'},
                'internal_imports': {'type': 'integer', 'description': 'relative, resolved in the tree, or a declared project namespace'},
                'external_packages': {
                    'type': 'array', 'description': 'most used first',
                    'items': {'type': 'object', 'properties': {
                        'package': {'type': 'string'}, 'uses': {'type': 'integer'},
                        'languages': {'type': 'array', 'items': {'type': 'string'}}}},
                },
                'stdlib_packages': {
                    'type': 'array',
                    'items': {'type': 'object', 'properties': {
                        'package': {'type': 'string'}, 'uses': {'type': 'integer'}}},
                },
                'top_importers': {
                    'type': 'array', 'description': 'import statements per file, most first',
                    'items': {'type': 'object', 'properties': {
                        'file': {'type': 'string'}, 'imports': {'type': 'integer'}}},
                },
            },
        },
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'imports://src',
        'description': 'Analyze all imports in src directory',
        'output_type': 'imports'
    },
    {
        'uri': 'imports://src?unused',
        'description': 'Find unused imports',
        'cli_flag': '?unused',
        'output_type': 'unused_imports'
    },
    {
        'uri': 'imports://src?circular',
        'description': 'Detect circular dependencies',
        'cli_flag': '?circular',
        'output_type': 'circular_dependencies'
    },
    {
        'uri': 'imports://src?violations',
        'description': 'Check layer violations (requires .reveal.yaml layers config)',
        'cli_flag': '?violations',
        'output_type': 'layer_violations'
    },
    {
        'uri': 'imports://src/main.py',
        'description': 'Analyze imports for a single file (no cycle detection)',
        'output_type': 'imports'
    },
    {
        'uri': 'imports://src?rank=fan-in',
        'description': 'Rank all files by fan-in — surface core abstractions and entry points',
        'output_type': 'fan_in_ranking'
    },
    {
        'uri': 'imports://src?rank=fan-in&top=20',
        'description': 'Top-20 files by fan-in',
        'output_type': 'fan_in_ranking'
    },
    {
        'uri': 'imports://src?rank=fan-in&lazy=exclude',
        'description': 'Fan-in over load-time (module-level) imports only: the architecture view',
        'output_type': 'fan_in_ranking'
    },
    {
        'uri': 'imports://src?circular&lazy=include',
        'description': 'Cycles counting function-level (lazy) imports too',
        'output_type': 'circular_dependencies'
    },
    {
        'uri': 'imports://src/utils.py?importers',
        'description': 'Who imports utils.py, from anywhere under the project root',
        'output_type': 'module_importers'
    },
    {
        'uri': 'imports://src?importers&tests=exclude',
        'description': 'Every module under src with its importers, test importers not counted',
        'output_type': 'importer_summary'
    },
    {
        'uri': 'imports://src?external',
        'description': 'Unresolved (third-party) and stdlib packages by use',
        'output_type': 'external_packages'
    },
]

_SCHEMA_NOTES = [
    'Supports multiple languages via plugin architecture',
    'Circular dependencies can indicate architectural issues',
    'Layer violations require .reveal.yaml configuration',
    'Unused import detection works with Python, JavaScript, Go, etc.',
    'False positives: imports that trigger side effects (e.g. decorator-based registration) will be flagged as unused — these are intentional and safe to ignore',
    'Fan-in ranking covers static imports only — decorator-based registration and importlib dynamic imports are not captured',
    'Function-level (lazy) imports are edges: ?circular and metadata.has_cycles leave them out by default, every other view counts them; &lazy=include|exclude|only overrides. Each answer states its rule in edge_rule (and a Rule: line in text). Python, JavaScript, TypeScript and TSX record import scope; edge_rule names the languages whose edges it could not classify',
    '?importers=FILE is the single-module reverse lookup and ?external the whole-tree package table (they replace depends:// and deps://, which still answer as retired spellings); use the raw graph for a query neither covers',
    'Scope (BACK-1054): every answer resolves at the project root (&root=, .reveal.yaml root: true, package marker, VCS root, else the requested directory) through the same cascade the retired depends:// used, and shows rows under the requested path; &scope=path makes the requested path the scan root. edge_rule names the root, its source, &scope, &tests, the edges each cascade stage found (via) and the languages no recall oracle gates',
    'Swift module and Ruby Zeitwerk convention edges (via module, convention) are counted as importers but never close a cycle',
]


def _shown_path(path: str, source: Optional[str]) -> str:
    """A row's path as the text views print it. The adapter's answer is already spelled from the
    requested directory (``_path_display``) and is printed as it is: re-spelling it against a FILE
    target turned that file's directory ``.`` into the file's name (BACK-2183). Only an absolute path
    (a result built by hand, BACK-1194) is relativized here."""
    if source and os.path.isabs(path):
        return to_relative_display(path, Path(source))
    return path


class ImportsRenderer:
    """Renderer for import analysis results."""

    @staticmethod
    def _render_edge_rule(result: dict) -> None:
        """The counting rule of an edge-derived answer, as the JSON states it (BACK-2077)."""
        for line in import_analysis.edge_rule_lines(result):
            print(f"  {line}\n")

    @staticmethod
    def _render_unused_imports(result: dict, verbose: bool) -> None:
        """Render unused imports results."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Unused Imports: {count}")
        print(f"{'='*60}\n")

        # A language with no import extractor (e.g. Kotlin, Swift, Scala) was
        # never analyzed at all — count == 0 in that case means "not checked,"
        # not "clean." Without this, the text renderer prints the same "✅ No
        # unused imports found!" for both cases, a false-confidence result
        # (BACK-431 feature-breadth pass); the JSON renderer already exposes
        # this via metadata.unsupported_extensions.
        unsupported = result.get('metadata', {}).get('unsupported_extensions') or {}
        if unsupported:
            exts = ', '.join(f'{ext} ({n} file{"s" if n != 1 else ""})' for ext, n in sorted(unsupported.items()))
            print(f"  ⚠ Not analyzed — no import extractor for: {exts}\n")

        not_checked = result.get('metadata', {}).get('unused_not_checked_extensions') or {}
        note = unused_not_checked_line(not_checked)
        if note:
            print(f"  {note}\n")

        # scanned_files (files with a working extractor), not total_files
        # (files with >=1 import statement) — a file can be fully, correctly
        # analyzed and still have zero imports (BACK-431: real WordPress
        # source with no `use`/`require` at all), and total_files would
        # wrongly read as "unchecked" in that case.
        judged_files = result.get('metadata', {}).get('scanned_files', 0) - sum(not_checked.values())
        if count == 0 and judged_files > 0:
            scope = f" in the {judged_files} checked file(s)" if not_checked else ""
            ImportsRenderer._render_no_unused(result, scope)
        elif count == 0:
            pass
        else:
            if verbose:
                for imp in result['unused']:
                    print(f"  {imp['file']}:{imp['line']} - {describe_unused(imp)}")
            else:
                for imp in result['unused'][:10]:
                    print(f"  {imp['file']}:{imp['line']} - {describe_unused(imp)}")
                if count > 10:
                    print(f"\n  ... and {count - 10} more unused imports")
                    print(f"  Run with --verbose to see all {count} unused imports\n")

    @staticmethod
    def _render_no_unused(result: dict, scope: str) -> None:
        """Qualify zero unused observations against required discovery loss."""
        if _discovery_incomplete(result):
            print(f"  No unused imports observed{scope} in the available inputs; analysis is incomplete.\n")
        else:
            print(f"  ✅ No unused imports found{scope}!\n")

    @staticmethod
    def _render_no_cycles(result: dict) -> None:
        """Qualify zero observed cycles against the available resolution population."""
        regime = result.get('metadata', {}).get('autoload_regime')
        total_imports = result.get('metadata', {}).get('total_imports', 0)
        scanned_files = result.get('metadata', {}).get('scanned_files', 0)
        if _discovery_incomplete(result):
            print("  No circular dependencies observed in the available graph; analysis is incomplete.\n")
        elif regime:
            # BACK-1245: an unqualified green check reads as "verified
            # acyclic" when there's barely an explicit import graph to
            # have cycles in -- disclose the denominator instead.
            print(
                f"  ✅ No circular dependencies found among {total_imports} explicit "
                f"import(s) across {scanned_files} file(s).\n"
            )
            print(f"  {autoload_regime_warning(regime)}\n")
        else:
            print("  ✅ No circular dependencies found!\n")

    @staticmethod
    def _render_circular_dependencies(result: dict, verbose: bool) -> None:
        """Render circular dependency groups (one entry per SCC)."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Circular Dependencies: {count} cycle group{'s' if count != 1 else ''}")
        print(f"{'='*60}\n")
        ImportsRenderer._render_edge_rule(result)

        if count == 0:
            ImportsRenderer._render_no_cycles(result)
            return

        groups = result['cycles']
        cycle_paths = result.get('cycle_paths', [])
        shown_groups = groups if verbose else groups[:5]
        shown_paths = cycle_paths[:len(shown_groups)] if cycle_paths else []
        for i, group in enumerate(shown_groups, 1):
            n = len(group)
            labels = [_module_label(p) for p in group]
            if verbose or n <= 4:
                label = ', '.join(labels)
            else:
                label = ', '.join(labels[:3]) + f'  [+{n - 3} more files]'
            print(f"  {i}. {n} file{'s' if n != 1 else ''}  {label}")
            if verbose and i - 1 < len(shown_paths):
                path_labels = [_module_label(p) for p in shown_paths[i - 1]]
                print(f"     cycle: {' → '.join(path_labels)}")
        if not verbose and count > 5:
            print(f"\n  ... and {count - 5} more groups")
            print(f"  Run with --verbose to see all {count} groups\n")
        if not verbose and cycle_paths:
            print(f"\n  Tip: add &verbose to see cycle edge sequences (A→B→C→A)")

    @staticmethod
    def _render_layer_violations(result: dict, verbose: bool) -> None:
        """Render layer violation results."""
        count = result['count']
        note = result.get('note', '')
        not_configured = count == 0 and note and 'requires' in note.lower()

        print(f"\n{'='*60}")
        if not_configured:
            print(f"Layer Violations: NOT CONFIGURED")
        else:
            print(f"Layer Violations: {count}")
        print(f"{'='*60}\n")
        ImportsRenderer._render_edge_rule(result)

        if not_configured:
            print(f"  ℹ️  {note}\n")
            print(f"  Add layer rules to .reveal.yaml to enable this check.\n")
        elif count == 0:
            if _discovery_incomplete(result):
                print("  No layer violations observed in the available graph; analysis is incomplete.\n")
            else:
                print(f"  ✅ {note or 'No violations found'}\n")
        else:
            violations = result.get('violations', [])
            shown = violations if verbose else violations[:10]
            for v in shown:
                print(f"  {v['from_file']} -> {v['to_file']}  [{v['layer']}] {v['reason']}")
            if not verbose and count > 10:
                print(f"\n  ... and {count - 10} more violations")
                print(f"  Run with --verbose to see all {count} violations\n")

    @staticmethod
    def _render_cycle_summary(result: dict, display_path: str) -> None:
        """Render observed cycles without declaring completeness after discovery loss."""
        metadata = result.get('metadata', {})
        total_files = metadata.get('total_files', 0)
        total_imports = metadata.get('total_imports', 0)
        has_cycles = metadata.get('has_cycles', False)
        if _discovery_incomplete(result) and not has_cycles:
            print("  Cycles Found:  Unknown (directory discovery incomplete)")
        elif total_files <= 1 and Path(display_path).is_dir():
            print("  Cycles Found:  N/A (only one file scanned — a cycle needs at least two)")
        elif total_files <= 1:
            print("  Cycles Found:  N/A (single-file scan — use imports://dir/ to detect cycles)")
        elif not total_imports:
            print("  Cycles Found:  N/A (no imports found)")
        else:
            print(f"  Cycles Found:  {'❌ Yes' if has_cycles else '✅ No'}")

    @staticmethod
    def _render_import_summary(result: dict, resource: str) -> None:
        """Render import analysis summary."""
        metadata = result.get('metadata', {})
        total_files = metadata.get('total_files', 0)
        total_imports = metadata.get('total_imports', 0)

        display_path = result.get('source', resource)

        print(f"\n{'='*60}")
        print(f"Import Analysis: {display_path}")
        print(f"{'='*60}\n")
        print(f"  Total Files:   {total_files}")
        print(f"  Total Imports: {total_imports}")
        ImportsRenderer._render_cycle_summary(result, display_path)
        print()
        ImportsRenderer._render_edge_rule(result)

        # Honesty note: recognized code files whose language has no import
        # extractor were scanned but contribute nothing — say so instead of
        # letting a low/zero count read as "clean".
        unsupported = metadata.get('unsupported_extensions') or {}
        if unsupported:
            skipped_total = sum(unsupported.values())
            exts = ', '.join(f"{ext} ({n})" for ext, n in unsupported.items())
            print(f"  ⚠️  {skipped_total} code file(s) skipped — no import support for: {exts}")
            print("      (these are not counted above; import graph excludes them)")
            print()

        # Honesty note (BACK-982): a supported file that tree-sitter could not
        # parse silently contributed zero imports/symbols above -- indistinguishable
        # from a genuinely empty file without this. Also means Cycles Found can
        # under-report: a real cycle running through one of these is invisible.
        files_lost_count = metadata.get('files_lost_count', 0)
        lost = set(metadata.get('files_lost', []))
        files_failed_count = metadata.get('files_failed_count', 0) - files_lost_count
        if files_failed_count:
            # Their recovered imports ARE in the graph (BACK-1460); only what sat
            # inside the error region is missing (BACK-1598 wording).
            print(f"  ⚠️  {files_failed_count} file(s) parsed with errors — their imports may be incomplete")
            print("      (import/cycle results can under-report; unused imports not checked in them)")
            parse_failed = [fp for fp in metadata.get('files_failed', []) if fp not in lost]
            for fp in parse_failed[:10]:
                print(f"      - {fp}")
            if files_failed_count > 10:
                print(f"      ... and {files_failed_count - 10} more")
            print()
        # A file lost to a dead pool worker was never parsed (BACK-1753).
        if files_lost_count:
            print(f"  ⚠️  {files_lost_count} file(s) not analyzed — a pool worker died")
            print("      (their imports and structure are missing; results can under-report)")
            for fp in sorted(lost)[:10]:
                print(f"      - {fp}")
            if files_lost_count > 10:
                print(f"      ... and {files_lost_count - 10} more")
            print()
        # The scanned path, not the renderer's `resource` argument, which reaches
        # here as '.' and widened a copy-pasted query to the whole cwd (BACK-1508).
        scope = cwd_path('', str(display_path))
        print("Query options:")
        print(f"  reveal 'imports://{scope}?unused'       - Find unused imports")
        print(f"  reveal 'imports://{scope}?circular'     - Detect circular deps")
        print(f"  reveal 'imports://{scope}?violations'   - Check layer violations")
        print(f"  reveal 'imports://{scope}?rank=fan-in'  - Rank files by fan-in (core abstractions)")
        print()

    @staticmethod
    def _render_fan_in(result: dict, resource: str) -> None:
        """Render rank=fan-in output — files ranked by number of importers."""
        entries = result.get('entries', [])
        total = result.get('total', 0)
        source = result.get('source', resource)

        print(f"\nFan-in ranking: {source}")
        print(f"Files: {len(entries)} of {total}  (fan-in = number of files that import this file)")
        print()
        ImportsRenderer._render_edge_rule(result)

        if not entries:
            print("  No import data found.")
            return

        shown = [_shown_path(e['file'], source) for e in entries]
        col_w = max(min(60, max(len(fpath) for fpath in shown) + 2), 20)

        print(f"  {'FILE':<{col_w}}  {'FAN-IN':>7}  {'FAN-OUT':>8}")
        print(f"  {'-'*col_w}  {'-'*7}  {'-'*8}")
        for e, fpath in zip(entries, shown):
            print(f"  {fpath:<{col_w}}  {e['fan_in']:>7}  {e['fan_out']:>8}")
        print()
        regime = result.get('metadata', {}).get('autoload_regime')
        if regime:
            print(f"  {autoload_regime_warning(regime)}")
        else:
            print("  Note: static imports only — files loaded via dynamic dispatch")
            print("  (importlib, require(), Class.forName, autoload, etc.) show lower fan-in than actual.")
        print()

    @staticmethod
    def _render_file_importers(result: dict, resource: str) -> None:
        rows = result.get('importers', [])
        print(f"\nImporters of {result.get('target', resource)}: {result.get('count', len(rows))}")
        print()
        ImportsRenderer._render_edge_rule(result)
        for row in rows:
            where = f":{row['line']}" if row.get('line') else ''
            tags = ', '.join(filter(None, [', '.join(row.get('via') or []), ', '.join(row.get('scope') or [])]))
            module = f"  {row['module']}" if row.get('module') else ''
            print(f"  {row['file']}{where}{module}" + (f"  [{tags}]" if tags else ''))
        if not rows:
            print('  No importers found.')
        print()

    @staticmethod
    def _render_importers(result: dict, resource: str, verbose: bool) -> None:
        """Render ?importers: one file's importers (module_importers) or every module's (importer_summary)."""
        if result.get('type') == 'module_importers':
            ImportsRenderer._render_file_importers(result, resource)
            return
        entries = result.get('entries', [])
        shown = entries if verbose else entries[:20]
        print(f"\nImporters: {result.get('source', resource)}")
        print(f"Modules with importers: {result.get('total', len(entries))}")
        print()
        ImportsRenderer._render_edge_rule(result)
        for entry in shown:
            print(f"  {entry['file']}  ({entry['fan_in']})")
            for importer in entry['importers'] if verbose else entry['importers'][:5]:
                print(f"      {importer}")
            if not verbose and len(entry['importers']) > 5:
                print(f"      ... and {len(entry['importers']) - 5} more")
        if len(entries) > len(shown):
            print(f"\n  ... and {len(entries) - len(shown)} more modules (--verbose or --format json lists all)")
        if not entries:
            print('  No module under this path has an importer.')
        print()

    @staticmethod
    def _render_dot(result: dict) -> None:
        """?importers&format=dot: one importer -> module edge per listed importer; warnings go to
        stderr so stdout stays valid Graphviz (as every dot view does)."""
        for line in meta_warning_lines(result):
            print(line, file=sys.stderr)

        def quoted(path: str) -> str:
            return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'

        print('digraph modules {')
        print('  rankdir=LR;')
        print('  node [shape=box fontname="monospace"];')
        for entry in result.get('entries', []):
            for importer in entry['importers']:
                print(f'  {quoted(importer)} -> {quoted(entry["file"])};')
        print('}')

    @staticmethod
    def _render_external(result: dict, resource: str, verbose: bool) -> None:
        """Render ?external: the package table, most used first (20 per list unless --verbose)."""
        external, stdlib = result.get('external_packages', []), result.get('stdlib_packages', [])
        print(f"\nPackages: {result.get('source', resource)}")
        print(f"  {result.get('total_imports', 0)} import(s) in {result.get('total_files', 0)} file(s): "
              f"{result.get('internal_imports', 0)} internal, {len(external)} unresolved package(s), "
              f"{len(stdlib)} stdlib package(s)")
        multi_stack = len({lang for entry in external for lang in entry.get('languages', [])}) > 1
        for title, entries in (('Unresolved packages (third-party or unresolved-local)', external),
                               ('Stdlib packages', stdlib)):
            if not entries:
                continue
            shown = entries if verbose else entries[:20]
            print(f"\n{title}: {len(entries)}")
            for entry in shown:
                langs = f"  [{', '.join(entry.get('languages') or []) or '?'}]" if multi_stack and 'languages' in entry else ''
                print(f"  {entry['package']:<30} {entry['uses']:>4} use(s){langs}")
            if len(entries) > len(shown):
                print(f"  ... and {len(entries) - len(shown)} more (--verbose or --format json lists all)")
        if not external and not stdlib:
            print('\n  No unresolved or stdlib imports found.')
        print()

    @staticmethod
    def _render_entrypoints(result: dict, resource: str) -> None:
        """Render ?entrypoints output — files with fan-in=0 (nothing imports them)."""
        entries = result.get('entries', [])
        total_scanned = result.get('total_scanned', 0)
        source = result.get('source', resource)

        print(f"\nEntry points: {source}")
        print(f"Files: {len(entries)} of {total_scanned}  (fan-in=0: nothing imports these — entry points or dead code)")
        print()
        ImportsRenderer._render_edge_rule(result)

        if not entries:
            if _discovery_incomplete(result):
                print("  No entry points observed in the available graph; analysis is incomplete.")
            else:
                print("  No entry points found (every file is imported by at least one other).")
            return

        shown = [_shown_path(e['file'], source) for e in entries]
        col_w = max(min(60, max(len(fpath) for fpath in shown) + 2), 20)

        print(f"  {'FILE':<{col_w}}  {'FAN-OUT':>8}")
        print(f"  {'-'*col_w}  {'-'*8}")
        for e, fpath in zip(entries, shown):
            print(f"  {fpath:<{col_w}}  {e['fan_out']:>8}")
        print()
        regime = result.get('metadata', {}).get('autoload_regime')
        if regime:
            print(f"  {autoload_regime_warning(regime)}")
        else:
            print("  Note: static imports only — files loaded via dynamic dispatch")
            print("  (importlib, require(), Class.forName, autoload, etc.) are false positives here.")
        print()

    @staticmethod
    def _render_components(result: dict, resource: str) -> None:
        """Render ?components output — per-directory cohesion and coupling scores."""
        components = result.get('components', [])
        source = result.get('source', resource)

        print(f"\nComponent analysis: {source}")
        print(f"Components: {len(components)}  (cohesion = internal imports ÷ outgoing imports from component)")
        print()
        ImportsRenderer._render_edge_rule(result)

        if not components:
            print("  No components found.")
            return

        col_w = max(max(len(_shown_path(c['component'], source)) for c in components) + 2, 20)
        col_w = min(col_w, 55)

        print(f"  {'COMPONENT':<{col_w}}  {'FILES':>5}  {'INTERNAL':>8}  {'OUT':>5}  {'IN':>5}  {'COHESION':>9}")
        print(f"  {'-'*col_w}  {'-'*5}  {'-'*8}  {'-'*5}  {'-'*5}  {'-'*9}")

        for c in components:
            name = _shown_path(c['component'], source)
            bridge = c.get('top_bridge')
            bridge_note = f"  ← {Path(bridge).name}" if bridge else ''
            cohesion_pct = 'n/a' if c['cohesion'] is None else f"{c['cohesion'] * 100:.0f}%"
            print(f"  {name:<{col_w}}  {c['files']:>5}  {c['internal']:>8}  {c['outgoing']:>5}  {c['incoming']:>5}  {cohesion_pct:>9}{bridge_note}")

        print()
        print("  Note: low cohesion = files import heavily outside this directory (may not be a real component)")
        if result.get('cohesion_rule'):
            print(f"  Note: {result['cohesion_rule']}")
        print("  Note: static imports only — dynamic dispatch not captured")
        print()

    @staticmethod
    def render_structure(result: dict, format: str = 'text', verbose: bool = False, resource: str = '.') -> None:
        """Render import analysis results.

        Args:
            result: Structure dict from ImportsAdapter.get_structure()
            format: Output format ('text', 'json')
            verbose: Show detailed results
            resource: Resource path for display
        """
        if result.get('_format') == 'dot':
            ImportsRenderer._render_dot(result)
            return
        if format == 'json':
            print_json_result(result)
            return

        for line in meta_warning_lines(result):
            print(line)

        # verbose from query (?verbose) takes precedence over caller arg
        verbose = result.get('verbose', verbose)

        # Text format with progressive disclosure
        if 'type' in result:
            result_type = result['type']
            if result_type == 'unused_imports':
                ImportsRenderer._render_unused_imports(result, verbose)
            elif result_type == 'circular_dependencies':
                ImportsRenderer._render_circular_dependencies(result, verbose)
            elif result_type == 'layer_violations':
                ImportsRenderer._render_layer_violations(result, verbose)
            elif result_type == 'fan_in_ranking':
                ImportsRenderer._render_fan_in(result, resource)
            elif result_type == 'entrypoints':
                ImportsRenderer._render_entrypoints(result, resource)
            elif result_type == 'components':
                ImportsRenderer._render_components(result, resource)
            elif result_type in ('module_importers', 'importer_summary'):
                ImportsRenderer._render_importers(result, resource, verbose)
            elif result_type == 'external_packages':
                ImportsRenderer._render_external(result, resource, verbose)
            else:
                ImportsRenderer._render_import_summary(result, resource)
        else:
            print_json_result(result)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render file-specific imports.

        Args:
            result: Element dict from ImportsAdapter.get_element()
            format: Output format ('text', 'json')
        """
        if format == 'json':
            print_json_result(result)
            return

        # Text format - file imports
        print(f"Imports for: {result.get('file', 'unknown')}")
        imports = result.get('imports', [])
        if imports:
            for imp in imports:
                print(f"  • {imp['module']} (line {imp['line']})")
        else:
            print("  No imports found")


from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages  # noqa: E402


# ── BACK-489 P1: parallel per-file extraction ───────────────────────────────
# `_build_graph`'s per-file work (import/symbol extraction + optional AST
# structure) is independent across files — an embarrassingly-parallel map whose
# only shared step is the cheap graph-assembly reduce that follows. On large
# repos this map is ~94% of `reveal architecture`'s cost and is otherwise
# single-threaded (BACK-489). We fan it out across processes (tree-sitter parsing is fork-safe;
# measured 4.6x on a 12-core box for a 852-file TS subset). Results are
# consumed in submission order (ProcessPoolExecutor.map preserves order), so
# the assembled graph and structure list are byte-identical to the serial path.
_PARALLEL_MIN_FILES = 200   # below this, pool startup/IPC outweighs the win
_PARALLEL_MAX_WORKERS = 16  # cap so huge core counts don't oversubscribe/thrash


def _parallel_worker_count(n_files: int) -> int:
    """Workers to use for `n_files`. 1 = run serially (no pool).

    `REVEAL_MAX_WORKERS` overrides everything (set to 1 to force the serial
    path — used by tests and for debugging); otherwise parallelize only above
    `_PARALLEL_MIN_FILES`, capped at `_PARALLEL_MAX_WORKERS` and the CPU count.
    """
    if n_files < _PARALLEL_MIN_FILES:
        return pool_worker_count(1)
    return pool_worker_count(min(os.cpu_count() or 1, _PARALLEL_MAX_WORKERS))


def _extract_one_file(fp_str: str, want_structure: bool,
                      inputs: Optional[resolution.ResolutionInputs] = None):
    """Extract imports/symbols (+ optional AST structure) for a single file.

    Module-level and picklable so it runs unchanged under a
    `ProcessPoolExecutor` (fork *or* spawn). Returns
    `(fp_str, imports_or_None, symbols_or_None, structure_or_None, extraction, structure_failure_or_None,
    entry_or_None)`:
    `imports`/`symbols` are None when the file has no import extractor (mirrors
    the serial path only populating them for extractable files); `structure`
    is None when not requested or when analysis raised (`structure_failure` then
    names the error). Import extraction errors are NOT
    swallowed here — the serial path lets them propagate too. `extraction.parse_failed` is True
    when the extractor had one (i.e. the file's language IS supported) but
    tree-sitter could not parse it (`extractor.parse_failed`, BACK-982) — such
    a file's `imports`/`symbols` are an empty/partial result, not a confirmed-
    clean one, so callers (I001/I002, this adapter's own summary) must not
    treat it the same as a genuinely-clean file.

    With the cascade's project-wide *inputs* (BACK-1054) the file is read as the cascade reads it
    (PHP gets the constant index) and also indexed where it was parsed (``resolution.index_file``),
    so the main process never parses it again; ``entry`` is None without them or an extractor.
    """
    fp = Path(fp_str)
    imports = symbols = structure = structure_failure = entry = None
    extraction = None
    extractor = get_extractor(fp)
    if extractor is not None:
        if inputs is None:
            imports = extractor.extract_imports(fp)
        else:
            imports = resolution.extract_file(fp, extractor, inputs.constant_index)
        symbols = extractor.extract_symbols(fp)
        if hasattr(extractor, 'extract_exports'):
            symbols = symbols | extractor.extract_exports(fp)
        extraction = extractor.analysis
        if inputs is not None:
            entry = resolution.index_file(fp, extractor, imports, inputs.manifest_dirs)
    if want_structure:
        # Structure is a separate add-on (only requested via collect_structures=True).
        # analyze_file_outcome catches an analysis failure itself and returns it, so it
        # reaches the run's analysis_failed warning instead of reading as "this file has
        # no structure"; an exception that still escapes (a failed import, a bug) fails
        # the chunk, which _extract_files records per file (BACK-1059, BACK-1856).
        from .ast.analysis import analyze_file_outcome
        structure, structure_failure = analyze_file_outcome(fp_str)
    return fp_str, imports, symbols, structure, extraction, structure_failure, entry


def _extract_chunk(job: Tuple[List[str], bool, Optional[resolution.ResolutionInputs]]) -> list:
    """`_extract_one_file` over one chunk of paths: the pool's unit of work."""
    paths, want_structure, inputs = job
    return [_extract_one_file(fp_str, want_structure, inputs) for fp_str in paths]


def _recording_entries(rows, entries: Optional[Dict[Path, resolution.FileEntry]]):
    """``_extract_files`` rows without their last element, the file's ``FileEntry``, which lands in
    *entries* (a file with no extractor, or lost to a dead worker, has none)."""
    for fp, *rest, entry in rows:
        if entry is not None and entries is not None:
            entries[fp] = entry
        yield (fp, *rest)


def _lost_extraction(error: BaseException) -> ImportExtraction:
    """The extraction record of a file a dead pool worker lost: failed, with the
    cause, like a file its extractor could not parse (BACK-1726)."""
    return ImportExtraction(parse_failed=True, worker_lost=True, diagnostics={
        'parse': {'status': 'unavailable', 'reason': f"{type(error).__name__}: {error}"}})


def _path_display(base_path: Path) -> Callable[[Optional[str]], Optional[str]]:
    """Every path an imports answer prints, spelled from the requested directory (a file target's own
    directory): the requested file is named (BACK-1488), a file under the directory is relative to it,
    and any other file is spelled ``../`` from it. That covers a sibling of a file target (BACK-2183), a
    file outside the requested path under scope=root (``../tests/test_x.py``) and a target outside a
    pinned ``&root=`` or a ``&scope=path`` scan root (BACK-2184, BACK-2157), which fell back to the host
    path. Only a path on another Windows drive, which has no relative spelling, is printed as given."""
    base_dir = base_path if base_path.is_dir() else base_path.parent

    def rel(value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        shown = to_relative_display(value, base_dir)
        if not os.path.isabs(shown):
            return to_posix(shown)  # the string: a PurePath's as_posix() keeps a backslash on POSIX
        try:
            return to_posix(os.path.relpath(value, base_dir))
        except ValueError:  # another drive on Windows
            return shown
    return rel


def _spell_metadata_paths(metadata: Dict[str, Any],
                          rel: Callable[[Optional[str]], Optional[str]]) -> Dict[str, Any]:
    """The answer's copy of ``get_metadata()`` with its file lists spelled as the rows are (BACK-2185).

    ``get_metadata()`` keeps absolute ``files_failed``/``files_lost`` for its library readers
    (overview://, the architecture diff), which spell them against their own base; the answer printed
    them as host paths. ``extraction_diagnostics`` keys arrive relative to the target where they can
    be (``rel`` reads such a key from the same directory) and absolute otherwise."""
    for key in ('files_failed', 'files_lost'):
        if isinstance(metadata.get(key), list):
            metadata[key] = [rel(path) or path for path in metadata[key]]
    if isinstance(metadata.get('extraction_diagnostics'), dict):
        metadata['extraction_diagnostics'] = {
            rel(path) or path: causes for path, causes in metadata['extraction_diagnostics'].items()}
    return metadata


def _relativize_importer_paths(result: Dict[str, Any], rel: Callable[[Optional[str]], Optional[str]]) -> None:
    """The importer views (BACK-1054) name every file relative to the requested directory (a file
    target's own directory), as depends:// names them relative to its root."""
    if result.get('target'):
        result['target'] = rel(result['target'])
    for row in result.get('importers', []):
        row['file'] = rel(row['file'])
    for entry in result.get('entries', []):
        entry['file'] = rel(entry['file'])
        entry['importers'] = sorted(cast(str, rel(f)) for f in entry['importers'])


def _relativize_import_dicts(imports: List[Dict[str, Any]], rel: Callable[[Optional[str]], Optional[str]],
                             roots: Tuple[Path, Optional[Path]]) -> None:
    """``file`` and ``resolved`` of formatted import statements, and an absolute ``module`` in the
    project (under the requested path's directory or the scan root, ``roots``): a folded PHP constant
    include keeps its host path as the module, spelled as the ?importers=FILE row does. A module the
    author wrote absolute outside the project is source text, not a host path of ours, and is
    reported as written."""
    base_path, scan_root = roots
    project = (base_path if base_path.is_dir() else base_path.parent, scan_root)
    for imp in imports:
        if imp.get('file'):
            imp['file'] = rel(imp['file'])
        if imp.get('resolved'):
            imp['resolved'] = rel(imp['resolved'])
        module = imp.get('module')
        if module and os.path.isabs(module) and any(
                resolution.path_is_under(Path(module), where) for where in project if where):
            imp['module'] = rel(module)


def _relativize_imports_paths(result: Dict[str, Any], base_path: Path, scan_root: Optional[Path] = None) -> None:
    """Spell the file-path fields of a view's data with ``_path_display`` (the envelope's metadata
    and warnings are spelled in ``_build_response``). The raw structures get_structure() serializes
    to JSON leaked absolute host paths (analyst's filesystem layout/username), same gap as
    overview.py's `_relativize_paths` / deps.py's `_relativize_deps_paths` (BACK-1194 follow-up).
    BACK-1212. Mutates in place; dispatches on result['type'] since get_structure() returns a
    different shape per query param; the text renderers print what this leaves.
    """
    rel = _path_display(base_path)

    def relativize_import_dicts(imports: List[Dict[str, Any]]) -> None:
        _relativize_import_dicts(imports, rel, (base_path, scan_root))

    result_type = result.get('type')
    if result_type == 'imports':
        files = result.get('files')
        if isinstance(files, dict):
            relativized_files = {}
            for file_path, entries in files.items():
                relativize_import_dicts(entries)
                relativized_files[rel(file_path)] = entries
            result['files'] = relativized_files
    elif result_type == 'unused_imports':
        relativize_import_dicts(result.get('unused', []))
    elif result_type in ('fan_in_ranking', 'entrypoints'):
        # Every entry and component carries these keys; rel() leaves an empty value as it is.
        for entry in result.get('entries', []):
            entry['file'] = rel(entry['file'])
    elif result_type == 'components':
        for component in result.get('components', []):
            component['component'] = rel(component['component'])
            component['top_bridge'] = rel(component['top_bridge'])
    elif result_type in ('module_importers', 'importer_summary'):
        _relativize_importer_paths(result, rel)
    elif result_type == 'circular_dependencies':
        for key in ('cycles', 'cycle_paths'):
            groups = result.get(key)
            if groups:
                result[key] = [[rel(fp) for fp in group] for group in groups]
    # 'layer_violations' already relativizes (to_posix + relative_to
    # project_root in _format_violations); 'imports_error' has no file fields.


def _typed_params(params: Any) -> QueryParams:
    """Typed (subcommand) parameters as the URI spells them: an unset flag or option is absent, a
    set flag is present (the views read presence), a bare ``--importers`` (argparse's ``None`` for
    ``nargs='?'``) is ``?importers``."""
    items = list(params.peek_items() if isinstance(params, QueryParams) else dict(params).items())
    if isinstance(params, QueryParams) and not any(v is None or v is False for _k, v in items):
        return params
    typed = QueryParams()
    for key, value in items:
        if value is None and key == _IMPORTERS.name:
            value = True
        if value is None or value is False:
            continue
        typed[key] = True if key in _FLAG_NAMES else value
    return typed


def _named_candidates(name: str, base_dir: Path, root: Path) -> List[Path]:
    """The existing paths ``?importers=NAME`` can mean: relative to the requested directory and
    relative to the scan root (two spellings of one file collapse; two files stay two), or the
    absolute path itself. One owner for the answer and for the result type chosen before it."""
    named = Path(name).expanduser()
    found: List[Path] = []
    for candidate in ([named] if named.is_absolute() else [base_dir / named, root / named]):
        resolved = candidate.resolve()
        if resolved.exists() and resolved not in found:
            found.append(resolved)
    return found


def _scan_root_of(params: Any, target_path: Path) -> resolution.ScanRoot:
    """Where a request resolves: the requested path itself under ``&scope=path``, else the project
    root the shared climb finds (``resolution.choose_scan_root``: ``&root=``, markers, the inferred subtree)."""
    raw_root = params.get(_ROOT.name)  # a read: the build applies it
    if _SCOPE.read(params) == SCOPE_PATH:
        rejected = f'?root={raw_root} is ignored under scope=path' if raw_root else None
        return resolution.ScanRoot(target_path, 'path', override_rejected=rejected)
    return resolution.choose_scan_root(target_path, raw_root)


def _usage_rejection(result: Dict[str, Any]) -> bool:
    """A request the caller got wrong (a target that matches nothing): usage, exit 2."""
    return result.get('usage') is True and 'error' in result


# The views whose rows are findings: `--fail-on findings` exits 1 when the answer has one (BACK-1054
# slice S4: deps' gate over cycles and unused imports, on the imports views it composed).
_FINDINGS_VIEWS = frozenset({'circular_dependencies', 'unused_imports', 'layer_violations'})

# The parameters the build reads (where it resolves, under which file cap): one build, one value.
_BUILD_KEYS = (_SCOPE.name, _ROOT.name, _MAX_FILES.name)


def _validate_params(params: QueryParams) -> None:
    """Validate every supplied value; validation is not application (a preceding query mode may
    take priority, and the view that applies a value reads it)."""
    for key, value in params.peek_items():
        if key == 'rank' and value not in _SCHEMA_QUERY_PARAMS['rank']['values']:
            choices = ', '.join(_SCHEMA_QUERY_PARAMS['rank']['values'])
            raise ValueError(f'rank must be one of: {choices}; got {value!r}')
        if key == _LAZY.name:
            _LAZY.validate(value)
        if key == _FORMAT.name:
            _FORMAT.validate(value)
        for spec in _REQUEST_SPECS[1:] + PARAM_SPECS[3:5]:
            if key == spec.name:
                spec.validate(value)


def _incomplete(result: Dict[str, Any]) -> bool:
    """Whether an imports answer is short of its input: a file parsed with errors or lost to a dead
    worker, a walk the file cap cut short, a directory it could not list (D6: exit 3)."""
    metadata = result.get('metadata') or {}
    if metadata.get('files_failed_count') or metadata.get('files_lost_count'):
        return True
    if (metadata.get('scan_budget') or {}).get('capped'):
        return True
    return any(w.get('type') in ('analysis_incomplete', 'scan_capped')
               for w in (result.get('meta') or {}).get('warnings', []))


@register_adapter('imports')
@register_renderer(ImportsRenderer)
class ImportsAdapter(ResourceAdapter):
    """Analyze import relationships in codebases."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    # --head/--tail/--range cut the module rows of ?importers (and the other ranked views) and say so;
    # a directory ?importers answer is one row per module with ALL its importers, so this is the
    # bound on a corpus with hundreds of thousands of edges (swift), not a per-edge cap (BACK-2192).
    BUDGET_LIST_FIELD = 'entries'
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    CLI_QUERY_FLAGS = {'verbose': 'verbose', 'respect_gitignore': 'respect_gitignore=false'}  # `--verbose` == `&verbose` (BACK-1361)

    # D6 (BACK-1054): imports is a declared command, so a usage error exits 2 and an incomplete
    # analysis (a file parsed with errors or lost, a capped walk, a lost directory) exits 3.
    # --fail-on findings exits 1 when a findings view (_FINDINGS_VIEWS) has a row (slice S4).
    RESULT_TYPE = 'imports'
    FINDINGS_POLICIES = ('none', 'findings')
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = PARAM_SPECS

    def __init__(self, resource: str = '.', query: Optional[str] = None, *,
                 params: Optional[Any] = None, parse_extensions: Optional[frozenset] = None):
        """Initialize imports adapter.

        Args:
            resource: Directory or file path to analyze (e.g., 'src', '/abs/path')
            query: Query string portion (e.g., 'unused', 'circular=true')
            params: the subcommand's typed parameters (a flag left off is not supplied)
            parse_extensions: the extensions the walk keeps and parses, for a caller with its own
                build (depends://, a file target's own family: BACK-525 layer 4, BACK-1054 S6); None
                keeps every extension with an extractor plus recognized code without one (counted
                for the coverage warning, and against the file cap)
        """
        path = resource
        self.analysis = ImportAnalysis()
        # Populated only when _build_graph is called with collect_structures=True
        # (reveal architecture) — per-file AST structures from the shared walk.
        self._structures: List[Dict[str, Any]] = []
        # Handle both absolute and relative paths:
        # - netloc component from URI parsing (imports://relative/path → 'relative/path')
        # - absolute path (imports:///absolute/path → '/absolute/path')
        self._target_path: Optional[Path] = Path(path).resolve() if path else None
        self._query_params = _typed_params(params) if params is not None else parse_query_params(query or '')
        self.query_params = self._query_params  # the name the declared route reads (D6)
        self._warn_unknown_query_params(self._query_params)  # BACK-507
        _validate_params(self._query_params)
        self._local_names_cache: Optional[frozenset] = None  # BACK-1190, lazy
        self._project_namespaces_cache: Optional[set] = None  # BACK-1234, lazy
        # A walk that hid every candidate says so (BACK-2065); set by _build_graph.
        self._scope_hidden: Optional[WarningEntry] = None
        # Where _build_graph resolved and under which file cap (BACK-1054).
        self._scan: Optional[resolution.ScanRoot] = None
        self._scan_budget = ScanBudget(_MAX_FILES.default)
        self._parse_extensions = parse_extensions

    @staticmethod
    def result_type_for(params: Any) -> str:
        """The answer type the query selects, in get_structure's precedence (the path decides
        between the two ?importers types: ``result_type_at``)."""
        supplied = dict(_typed_params(params).peek_items()) if not isinstance(params, str) else {}
        if 'importers' in supplied:
            return 'importer_summary'
        for key, kind in (('unused', 'unused_imports'), ('circular', 'circular_dependencies'),
                          ('violations', 'layer_violations')):
            if key in supplied:
                return kind
        if supplied.get('rank') == 'fan-in':
            return 'fan_in_ranking'
        if 'entrypoints' in supplied:
            return 'entrypoints'
        if 'components' in supplied:
            return 'components'
        if 'external' in supplied:
            return 'external_packages'
        return 'imports'

    @classmethod
    def result_type_at(cls, params: Any, path: str) -> str:
        kind = cls.result_type_for(params)
        if kind != 'importer_summary':
            return kind
        named = dict(_typed_params(params).peek_items()).get('importers')
        target = Path(path).expanduser()
        if isinstance(named, str):
            base = target if target.is_dir() else target.parent
            found = _named_candidates(named, base, _scan_root_of(_typed_params(params), base.resolve()).root)
            target = found[0] if len(found) == 1 else base
        return 'module_importers' if target.is_file() else 'importer_summary'

    @staticmethod
    def public_diagnostic(result: Dict[str, Any]) -> Optional[str]:
        return str(result['error']) if _usage_rejection(result) else None

    @staticmethod
    def execution_facts(result: Any):
        from ..utils.results import AnalysisCompleteness, FailureCause, failure_execution_facts, result_execution_facts
        if not isinstance(result, dict):
            return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
        if _usage_rejection(result):
            return failure_execution_facts(FailureCause.INVALID_REQUEST)
        state = AnalysisCompleteness.INCOMPLETE if _incomplete(result) else AnalysisCompleteness.COMPLETE
        findings = result.get('type') in _FINDINGS_VIEWS and bool(result.get('count'))
        return result_execution_facts(result, completeness=state, findings=findings)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Analyze imports in directory or file.

        Args:
            **kwargs: Additional parameters (unused, circular, violations flags)

        Returns:
            Dictionary with import analysis results
        """
        target_path = self._target_path or Path('.').resolve()
        query_params = self._query_params
        self._target_path = target_path

        if not target_path.exists():
            return self._build_response('imports_error', error=f"Path not found: {target_path}")

        # Extract imports and build graph
        self._build_graph(target_path)
        return self._present(query_params, kwargs)

    def analyze(self) -> ImportAnalysis:
        """Build the graph this request resolves (its root, file cap and extension family) and return
        it unpresented, for a presenter with its own answer shape over the one engine (depends://,
        BACK-1054 S6). ``scan`` and ``scope_hidden`` describe this build; on a cache hit the
        analysis is shared, so a caller reads it and never changes it."""
        target_path = self._target_path or Path('.').resolve()
        self._target_path = target_path
        self._build_graph(target_path)
        return self.analysis

    @property
    def scan(self) -> Optional[resolution.ScanRoot]:
        """Where the last build resolved (None before one)."""
        return self._scan

    @property
    def scope_hidden(self) -> Optional[WarningEntry]:
        """What the last build's walk hid from the request's focus, judged by this request's walk
        (BACK-2065), never read from a cached build."""
        return self._scope_hidden

    def get_view(self, query: str) -> Dict[str, Any]:
        """Another view of the graph ``get_structure()`` built, without building it again: a
        composer that shows several views side by side reads them from one build (deps:// shows
        the default view, ?circular and ?unused, BACK-1054). ``query`` chooses the view and how it
        counts (``&lazy``, ``&tests``, ``&top``...); a parameter that would change the build
        (``&scope``, ``&root``, ``&max_files``) must equal the built one, else ValueError."""
        params = parse_query_params(query or '')
        self._warn_unknown_query_params(params)
        _validate_params(params)
        changed = [key for key in _BUILD_KEYS
                   if dict(params.peek_items()).get(key) != dict(self._query_params.peek_items()).get(key)]
        if changed:
            raise ValueError(f'get_view cannot change the build ({", ".join(changed)}): construct another adapter')
        target_path = self._target_path or Path('.').resolve()
        if not target_path.exists():
            return self._build_response('imports_error', error=f"Path not found: {target_path}")
        if self.analysis.graph is None:
            raise ValueError('get_view reads the graph get_structure() builds, and none was built')
        self._query_params = self.query_params = params
        return self._present(params, {})

    def _present(self, query_params: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """The answer the query asks for, from the built graph, with paths as the request spelled them."""
        target_path = self._target_path or Path('.').resolve()
        result = self._format_view(query_params, kwargs)
        _relativize_imports_paths(result, target_path, self._scan.root if self._scan else None)
        # Read where the view draws: on any other view the key is unread, and says so.
        if result.get('type') == 'importer_summary' and _FORMAT.read(query_params) == 'dot':
            result['_format'] = 'dot'
        # Read where the view expands: on any other view the flag is unread, and says so.
        if result.get('type') in _VERBOSE_VIEWS and ('verbose' in query_params or kwargs.get('verbose', False)):
            result['verbose'] = True
        return result

    def _format_view(self, query_params: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """The one view the query asks for, in precedence order (?importers first, BACK-1054)."""
        importers = _IMPORTERS.read(query_params)
        if importers is not None:
            result = self._format_importers(importers)
        elif 'unused' in query_params or kwargs.get('unused'):
            result = self._format_unused()
        elif 'circular' in query_params or kwargs.get('circular'):
            result = self._format_circular()
        elif 'violations' in query_params or kwargs.get('violations'):
            result = self._format_violations()
        elif query_params.get('rank') == 'fan-in':
            result = self._format_fan_in()
        elif 'entrypoints' in query_params:
            result = self._format_entrypoints()
        elif 'components' in query_params:
            result = self._format_components()
        elif 'external' in query_params:
            result = self._format_external()
        else:
            result = self._format_all()
        return result

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get imports for a specific file.

        Args:
            element_name: File name (e.g., 'main.py')
            **kwargs: Additional parameters

        Returns:
            Dictionary with imports for that file
        """
        if not self.analysis.graph:
            return None

        # Find matching file
        for file_path, imports in self.analysis.graph.files.items():
            if file_path.name == element_name:
                return {
                    'file': str(file_path),
                    'imports': [self._format_import(stmt) for stmt in imports],
                    'count': len(imports)
                }

        return None

    def integrity_warnings(self, base: Optional[Path] = None, *,
                           spell: Optional[Callable[[Optional[str]], Optional[str]]] = None) -> List[WarningEntry]:
        """The graph's disclosures, for the commands that build it through _build_graph
        rather than get_structure (overview, architecture): files parsed with errors
        (parse_failure_warning) and files a dead pool worker took down
        (worker_lost_warning), each under its own cause. Paths are relative to ``base``, or
        spelled by ``spell`` (imports' own answers, BACK-2185) when one is given."""
        from .ast.analysis import analysis_skipped_warning, traversal_failed_warning
        name = _spelled(spell)
        if spell is not None:
            base = None
        traversal = [PathFailure(name(path) if path else path, cause)
                     for path, cause in getattr(self.analysis.graph, 'traversal_failures', ())]
        structure_failures = [(name(path), cause) for path, cause in self.analysis.structure_failures]
        warnings = [traversal_failed_warning(traversal, base),
                    *file_loss_warnings(self.analysis, base, spell=spell),
                    analysis_skipped_warning(
                        structure_failures, base,
                        "analysis is incomplete; some functions and classes may be missing from the complexity and structure results")]
        return [w for w in warnings if w]

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about import analysis."""
        if not self.analysis.graph:
            return {'status': 'not_analyzed'}

        in_scope = [imports for f, imports in self.analysis.graph.files.items() if self._in_scope(f)]
        return {
            'total_imports': sum(len(imports) for imports in in_scope),
            'total_files': len(in_scope),
            # Files actually scanned with a working extractor — distinct from
            # total_files (files that happen to have >=1 import statement).
            # A file with a supported language but zero imports (common in
            # older procedural PHP/Ruby, found via real WordPress source
            # during the BACK-431 feature-breadth pass) legitimately has
            # total_files == 0 despite being fully, correctly analyzed; the
            # text renderer needs this count to tell "clean" from "unchecked."
            'scanned_files': sum(1 for f in self.analysis.scanned_files if self._in_scope(f)),
            # Cycles leave function-level imports out unless &lazy says otherwise (BACK-2077).
            'has_cycles': len(self._cycle_groups(self._edges(LAZY_EXCLUDE))) > 0,
            'cycles_lazy': self._lazy_mode(LAZY_EXCLUDE)[0],
            'analyzer': 'imports',
            # Recognized code files whose language has no import extractor yet.
            'unsupported_extensions': dict(sorted(self.analysis.unsupported_extensions.items())),
            # BACK-1398: scanned files whose language has an import extractor but
            # no unused-import detection -- their 0 unused is "not checked".
            'unused_not_checked_extensions': _unused_not_checked(self.analysis.scanned_files),
            # Files with a supported language that tree-sitter could not parse
            # (BACK-982) -- included in scanned_files but their imports/symbols
            # are incomplete, not confirmed-empty; has_cycles can under-report
            # when a cycle runs through one of these. Sorted+capped for stable,
            # bounded JSON/text output; the count alone (below) is exact.
            'extraction_diagnostics': {
                to_relative_display(fp, self._target_path): artifact.diagnostics
                for fp, artifact in self.analysis.extractions.items() if artifact.diagnostics
            },
            # files_failed is every file whose imports may be incomplete; files_lost is
            # the subset a dead pool worker took down before it was parsed (BACK-1753).
            'files_failed_count': len(self.analysis.files_failed),
            'files_failed': sorted(str(fp) for fp in self.analysis.files_failed)[:50],
            'files_lost_count': len(self.analysis.files_lost),
            'files_lost': sorted(str(fp) for fp in self.analysis.files_lost)[:50],
            # BACK-1245: None on every corpus except a detected convention-
            # autoloading framework (Rails/Django/Laravel) -- see
            # detect_autoload_regime()/autoload_regime_warning() above.
            'autoload_regime': detect_autoload_regime(self._target_path) if self._target_path else None,
            # BACK-1054: the one file cap the walk ran under (&max_files) and what it kept.
            'scan_budget': self._scan_budget_dict(),
        }

    def _scan_budget_dict(self) -> Dict[str, Any]:
        record = self.analysis.resolution
        accounting = record.scan_accounting if record is not None else None
        return {'scope': accounting.scope if accounting else 'source_candidates',
                'limit': self._scan_budget.limit,
                'total': accounting.total if accounting else None,
                'returned': accounting.returned if accounting else None,
                'exact': accounting.exact if accounting else None,
                'capped': bool(record.capped) if record is not None else False}

    def _row_files(self, graph: ImportGraph) -> set:
        """The files an answer has rows for: every scanned file and every edge target (which may
        live outside the parse corpus), whichever view, so a row never vanishes with &lazy or
        &tests; under scope=root only those under the requested path."""
        files = self.analysis.scanned_files | set(graph.files.keys()) | set(self._graph().reverse_deps.keys())
        return {f for f in files if self._in_scope(f)}

    def _cycle_groups(self, graph: ImportGraph) -> List[List[Path]]:
        """Cycle groups of ``graph`` that hold a row of this answer (all of each group is shown)."""
        return [group for group in graph.find_cycle_groups() if any(self._in_scope(f) for f in group)]

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for imports:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'imports',
            'description': 'Import graph analysis for detecting unused imports, circular dependencies, and layer violations',
            'uri_syntax': 'imports://<path>[?query]',
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': {},
            'cli_flags': ['--verbose'],
            'execution_policy': {'default_fail_on': ImportsAdapter.DEFAULT_FAIL_ON,
                                 'fail_on': list(ImportsAdapter.FINDINGS_POLICIES)},
            'supports_batch': False,
            'supports_advanced': False,
            'supported_languages': get_supported_languages(),
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for imports:// adapter.

        Help data loaded from reveal/adapters/help_data/imports.yaml
        to improve consistency and maintainability.
        """
        help_data = load_help_data('imports') or {}
        # Add dynamic supported languages to help data
        if help_data:
            help_data['supported_languages'] = get_supported_languages()
        return help_data

    def _extract_file_imports_and_symbols(self, file_path, extractor):
        """Extract imports and symbols from a single file using its extractor."""
        imports = extractor.extract_imports(file_path)
        symbols = extractor.extract_symbols(file_path)
        if hasattr(extractor, 'extract_exports'):
            exports = extractor.extract_exports(file_path)
            symbols = symbols | exports
        return imports, symbols

    def _extract_files(self, candidates: List[Path], want_structure: bool,
                       inputs: Optional[resolution.ResolutionInputs] = None):
        """Yield ``(Path, imports_or_None, symbols_or_None, structure_or_None, extraction,
        structure_failure_or_None, entry_or_None)``
        per candidate file, in candidate order.

        Fans the independent per-file extraction out across processes when the
        repo is large enough to pay back pool startup (`_parallel_worker_count`);
        otherwise runs it inline. Chunks are read in submission order, so the
        caller's assembly is identical either way. A file lost to a dead worker
        (which fails every pending chunk) is yielded with no imports and a failed
        extraction (`_lost_extraction`), so it reaches ``files_failed`` and the
        run's partial-parse warning instead of failing the whole run (BACK-1726).
        """
        workers = _parallel_worker_count(len(candidates))
        if workers <= 1:
            for fp in candidates:
                yield (fp, *_extract_one_file(str(fp), want_structure, inputs)[1:])
            return

        from concurrent.futures import ProcessPoolExecutor
        from ..logging_setup import worker_bootstrap

        n = len(candidates)
        # A few chunks per worker balances load without excessive IPC round-trips.
        chunksize = max(1, n // (workers * 8))
        chunks = [[str(fp) for fp in candidates[i:i + chunksize]] for i in range(0, n, chunksize)]
        with ProcessPoolExecutor(
            max_workers=workers, initializer=worker_bootstrap,
        ) as executor:
            futures = submit_each(executor, _extract_chunk, [(chunk, want_structure, inputs) for chunk in chunks])
            for chunk, future in zip(chunks, futures):
                try:
                    rows = future.result()
                except Exception as e:  # boundary-ok: broad-except -- future.result() re-raises whatever the worker raised: BrokenProcessPool when it died, or any exception an extractor threw on one file of the chunk; the chunk's files are recorded as failed extractions (_lost_extraction carries the cause) and reach files_failed and the partial-parse warning
                    rows = [(fp_str, None, None, None, _lost_extraction(e), None, None) for fp_str in chunk]
                for fp_str, *rest in rows:
                    yield (Path(fp_str), *rest)

    @staticmethod
    def _discover_candidate_files(
        target_path: Path, supported_exts: frozenset, code_exts: frozenset, *,
        traversal_failures: Optional[List[PathFailure]] = None,
        hidden: Optional[Dict[str, int]] = None,
    ) -> Tuple[List[Path], Dict[str, List[Path]]]:
        """Walk target_path for candidate code files (serial, cheap: no parsing).

        One resolution walk (BACK-1580, ``analyzers.imports.file_index``) yields both the
        graph's files and a ``basename -> [full paths]`` index of every file an import can
        point to (BACK-491: C/C++ include targets such as .inc/.tcc must resolve too), so
        ``#include`` resolution is a dict lookup. Gitignored and --exclude'd files stay in
        the index as targets but are not graph nodes (BACK-1386, BACK-1495); REVEAL_IGNORE
        drops a file from both (BACK-1362); declaration-only stubs are not nodes (BACK-1467).
        *hidden* receives the walk's hidden-entry tally (BACK-2065).
        """
        files = import_analysis.discover(import_analysis.ScanScope(target_path, supported_exts, code_exts))
        if traversal_failures is not None:
            traversal_failures.extend(files.traversal_failures)
        if hidden is not None:
            hidden.update(files.hidden)
        return list(files.candidates), files.index

    def _process_extracted_files(
        self,
        candidates: List[Path],
        collect_structures: bool,
        on_file_processed: Optional[Callable[[Path], None]],
        supported_exts: frozenset,
        code_exts: frozenset,
        inputs: Optional[resolution.ResolutionInputs] = None,
        entries: Optional[Dict[Path, resolution.FileEntry]] = None,
    ) -> List[ImportStatement]:
        """Run per-file extraction (parallel on large repos, else serial),
        consumed in candidate order so assembly is deterministic. Populates
        self.analysis.symbols_by_file/_scanned_files/_unsupported_extensions/_structures/
        _files_failed and returns the collected import statements; with the cascade's
        *inputs*, each extracted file's ``FileEntry`` lands in *entries*.
        """
        files: List[Path] = []
        all_imports: List[ImportStatement] = []
        structures: List[Dict[str, Any]] = []
        unextractable: Dict[str, int] = {}
        failed_files: List[Path] = []
        lost_files: List[Path] = []
        structure_failures: List[Tuple[str, str]] = []

        for fp, imports, symbols, structure, extraction, structure_failure in _recording_entries(
                self._extract_files(candidates, collect_structures, inputs), entries):
            if extraction is not None and extraction.worker_lost:
                # Lost before its extractor ran, so "no import extractor" is unknown for
                # it: failed either way, never silently unsupported (BACK-1752).
                if fp.suffix in supported_exts:
                    files.append(fp)
                    self.analysis.extractions[fp] = extraction
                failed_files.append(fp)
                lost_files.append(fp)
            elif fp.suffix in supported_exts:
                files.append(fp)
                if imports is not None:
                    self.analysis.symbols_by_file[fp] = symbols
                    all_imports.extend(imports)
                if extraction is not None:
                    self.analysis.extractions[fp] = extraction
                    if extraction.parse_failed:
                        failed_files.append(fp)
            else:
                ext = fp.suffix.lower()
                if ext in code_exts:
                    unextractable[ext] = unextractable.get(ext, 0) + 1
            if collect_structures and structure:
                structures.append(structure)
            if structure_failure:
                structure_failures.append((str(fp), structure_failure))
            if on_file_processed:
                on_file_processed(fp)

        self.analysis.scanned_files = set(files)
        self.analysis.unsupported_extensions = unextractable
        self._structures = structures
        self.analysis.files_failed = failed_files
        self.analysis.files_lost = lost_files
        self.analysis.structure_failures = structure_failures
        return all_imports

    def _scan_root_for(self, target_path: Path) -> resolution.ScanRoot:
        return _scan_root_of(self._query_params, target_path)

    def _walk_extensions(self) -> Tuple[frozenset, frozenset]:
        """The extensions the walk keeps and parses, and the recognized-code extensions without an
        import extractor it also keeps, to warn honestly (instead of a silent 0) when a scan hits,
        e.g., Swift or Scala. A caller's own family (``parse_extensions``, depends://) is kept
        alone, so the file cap counts only it."""
        if self._parse_extensions is not None:
            return self._parse_extensions, frozenset()
        return frozenset(get_all_extensions()), get_code_extensions()

    def _build_graph(
        self,
        target_path: Path,
        on_file_processed: Optional[Callable[[Path], None]] = None,
        collect_structures: bool = False,
    ) -> None:
        """Build the import graph a request about ``target_path`` reads (multi-language).

        The graph is resolved at the scan root ``_scan_root_for`` picks (the project root, or
        the path itself under ``&scope=path``), through depends://'s cascade
        (``analyzers/imports/resolution.py``, BACK-1054): direct resolution, the PHP constant
        index, namespace, member and Swift module fan-out, Zeitwerk convention edges, each edge
        tagged with the stage that found it. The walk keeps at most ``&max_files`` source files
        (one ScanBudget, disclosed). ``&scope``, ``&tests`` and ``&lazy`` choose rows and edges at
        presentation; none of them changes the build or its cache key.

        Only static imports are captured. Dynamic dispatch — Python's
        importlib.import_module, JS require(), Java Class.forName, Ruby autoload,
        and similar patterns — is invisible to this graph. All query modes
        (fan-in, entrypoints, unused, circular, violations) share this limitation.

        Per-file import/symbol extraction, the file's part of the cascade's indices and, when
        requested, AST structure analysis are independent across files and run in parallel
        across processes on large repos — see `_extract_one_file` / the module-level BACK-489 P1
        note. The project-wide inputs extraction reads (PHP constants, Swift manifests, gemspec
        roots) are built first, the resolution after; results are consumed in file order so
        output is identical to a serial run.

        Args:
            target_path: Directory or file the request is about
            on_file_processed: Optional callback invoked once per code file
                (import-extractable or not), in deterministic file order, after
                that file's extraction. A lightweight per-file notification hook
                (structure is delivered via ``collect_structures`` below, not
                this callback).
            collect_structures: When True, also run AST structure analysis
                (`analyze_file`) on every code file during the same parallel
                pass and store the truthy results in ``self._structures`` — lets
                `reveal architecture` get per-file complexity structures without
                a second full-repo walk/parse. When False (default), no
                structure analysis is done.

        Caches (BACK-834, BACK-2082, BACK-2109): when `collect_structures` is False and no
        `on_file_processed` callback was given, the resolved graph is cached on disk keyed by a
        fingerprint of the scan root, source membership, resolution targets and the build's file
        cap, and inside a host request it is also kept in memory (``_GRAPH_MEMO``, keyed by the
        root alone, validated by the tree stamp). A build that lost a file for a reason its
        content did not cause is returned, never stored (BACK-2083).
        """
        supported_exts, code_exts = self._walk_extensions()
        self._scan = scan = self._scan_root_for(target_path)
        root = scan.root
        self._scan_budget = ScanBudget(_MAX_FILES.read(self._query_params))
        focus = None if root == target_path else target_path
        files = import_analysis.discover(import_analysis.ScanScope(
            root, supported_exts, code_exts, cap=self._scan_budget.limit, focus=focus))
        candidates, file_index = list(files.candidates), files.index
        if focus is not None and target_path.is_file() and target_path not in candidates and (
                target_path.suffix in supported_exts or target_path.suffix.lower() in code_exts):
            # A file the request names is analyzed even when the root's walk leaves it out (a
            # declaration stub, BACK-1467; an ignored file), as a walk of the file alone keeps it.
            candidates.append(target_path)
        traversal_failures = list(files.traversal_failures)
        # Discovery runs on a cache hit too, so the disclosure is never a cached one.
        self._scope_hidden = hidden_entries_warning(files.hidden, files.analyzed)

        cacheable = not collect_structures and on_file_processed is None
        key = _graph_cache_key(candidates, file_index, root, traversal_failures,
                               self._scan_budget.limit, self._parse_extensions) if cacheable else None
        cached = _cached_graph(root, key)
        if cached is not None:
            self.analysis = cached
            return

        resolved = self._extract_and_resolve(files, candidates, focus, collect_structures, on_file_processed,
                                             supported_exts, code_exts)

        # A file lost to a dead worker or unreadable this run is not the tree's answer (BACK-2083).
        if key is not None and self.analysis.cacheable and not resolved.traversal_failures:
            disk_cache.put(_ADAPTER_IMPORT_GRAPH_NAMESPACE, key, self.analysis)
        if key is not None and not resolved.traversal_failures:
            _remember_graph(root, key, self.analysis)

    def _extract_and_resolve(self, files: import_analysis.ImportFileSet, candidates: List[Path],
                             focus: Optional[Path], collect_structures: bool,
                             on_file_processed: Optional[Callable[[Path], None]],
                             supported_exts: frozenset, code_exts: frozenset) -> resolution.ProjectResolution:
        """The uncached build: the cascade's project-wide inputs, the (parallel) per-file pass, then
        the cascade over the files' entries; fills ``self.analysis``."""
        assert self._scan is not None
        root = self._scan.root
        self.analysis = ImportAnalysis()
        resolver = resolution.ProjectResolver(cap=self._scan_budget.limit, focus=focus)
        resolver.result.scan_root = root
        resolver.record_discovery(files)
        parse_corpus = [fp for fp in candidates if fp.suffix in supported_exts]
        inputs = resolver.prepare(parse_corpus, root)
        entries: Dict[Path, resolution.FileEntry] = {}
        self._process_extracted_files(
            candidates, collect_structures, on_file_processed, supported_exts, code_exts, inputs, entries)
        resolved = resolver.resolve_entries(root, [fp for fp in parse_corpus if fp in entries], files.index,
                                            entries, inputs)
        self.analysis.graph = resolved.graph
        self.analysis.resolution = resolved
        return resolved

    def _build_response(self, response_type: str, **data_fields) -> Dict[str, Any]:
        """Build standardized adapter response with common structure.

        Args:
            response_type: Type of response (e.g., 'imports', 'unused_imports')
            **data_fields: Data fields to include in response

        Returns:
            Standardized response dict with contract_version, type, source, etc.
        """
        display = self._display()
        # Keep legacy file/worker diagnostics in their existing metadata and text paths.
        warnings = [warning for warning in self.integrity_warnings(spell=display)
                    if warning.get('type') == 'analysis_incomplete']
        if self._scope_hidden:
            warnings.append(self._scope_hidden)
        warnings.extend(self._scan_warnings())
        response = ResultBuilder.create(
            result_type=response_type,
            source=str(self._target_path),
            source_type='directory' if self._target_path and self._target_path.is_dir() else 'file',
            contract_version=CONTRACT_VERSION,
            data=data_fields,
            warnings=warnings,
        )
        response['metadata'] = metadata = _spell_metadata_paths(self.get_metadata(), display)
        failed = metadata.get('files_failed')
        if isinstance(failed, list):
            # get_metadata keeps the first 50 paths; the count is exact (BACK-1551).
            note_truncation(response, 'metadata.files_failed', len(failed),
                            metadata['files_failed_count'], 'auto_cap',
                            hint='the first 50 by path; files_failed_count is exact')
        return response

    def _display(self) -> Callable[[Optional[str]], Optional[str]]:
        """How this answer spells a path (``_path_display``): every view's rows and its envelope."""
        return _path_display(self._target_path or Path('.').resolve())

    def _lazy_mode(self, default: str) -> Tuple[str, bool]:
        """The &lazy value this view applies, and whether it is the view's ``default``."""
        raw = self._query_params.get(_LAZY.name)  # a read: the view applies it
        return (default, True) if raw is None else (_LAZY.validate(raw), False)

    def _graph(self) -> ImportGraph:
        if self.analysis.graph is None:
            raise ValueError('Import analysis requires a built graph before presentation')
        return self.analysis.graph

    def _edges(self, default: str) -> ImportGraph:
        """The graph view an edge-derived answer counts: &lazy, else the view's default, then
        &scan-root containment (BACK-2251: an edge to a file outside the scan root is not counted), then
        &tests=exclude (importers under a test path dropped, ``path_utils.is_test_path``)."""
        view = self._graph().edge_view(self._lazy_mode(default)[0])
        if self._scan is not None:
            view = view.within_root(self._scan.root)
        return view.without_test_importers() if self._tests_excluded() else view

    def outside_root_edge_count(self) -> int:
        """The edges the answer left out because their target is outside the scan root (BACK-2251)."""
        return self._graph().outside_root_edges(self._scan.root) if self._scan is not None else 0

    def _tests_excluded(self) -> bool:
        return bool(_TESTS.read(self._query_params) == 'exclude')

    def _scope_is_root(self) -> bool:
        return bool(_SCOPE.read(self._query_params) == SCOPE_ROOT)

    def _base_dir(self) -> Path:
        target = self._target_path or Path('.').resolve()
        return target if target.is_dir() else target.parent

    def _in_scope(self, path: Path) -> bool:
        """Whether ``path`` is a row of this answer: every file under the scan root when the requested
        path is the scan root, else the requested file or files under the requested directory."""
        target = self._target_path
        if target is None or self._scan is None:
            return True
        if self._scan.source == 'path' or self._scan.root == target:
            return resolution.path_is_under(path, self._scan.root)
        return path == target or (target.is_dir() and resolution.path_is_under(path, target))

    def _resolved_at(self, cycles: bool = False) -> import_analysis.ResolvedAt:
        scan = self._scan or resolution.ScanRoot(self._target_path or Path('.').resolve(), 'path')
        return import_analysis.ResolvedAt(
            root=to_posix(os.path.relpath(scan.root, self._base_dir())), root_source=scan.source,
            scope=_SCOPE.read(self._query_params), tests=_TESTS.read(self._query_params),
            gated=resolution.IMPORT_RECALL_GATED, cycles=cycles,
            outside_root=self._graph().outside_root_edges(scan.root))

    def _edge_rule(self, default: str, subject: str, *, tests_counted: bool = True,
                   cycles: bool = False) -> Dict[str, Any]:
        """The rule (JSON and text) of an answer counted on ``self._edges(default)``."""
        lazy, lazy_default = self._lazy_mode(default)
        return import_analysis.edge_rule(
            self._graph(), lazy, lazy_default=lazy_default, subject=subject,
            scope='scan_root' if self._scope_is_root() else 'scanned_path',
            tests_counted=tests_counted and not self._tests_excluded(),
            resolved_at=self._resolved_at(cycles), counted=self._edges(default))

    def _format_all(self) -> Dict[str, Any]:
        """Format all imports (default view)."""
        if not self.analysis.graph:
            return {'imports': []}

        imports_by_file = {
            str(file_path): [self._format_import(stmt) for stmt in imports]
            for file_path, imports in self.analysis.graph.files.items() if self._in_scope(file_path)
        }

        return self._build_response(
            'imports', files=imports_by_file,
            edge_rule=self._edge_rule(LAZY_EXCLUDE, 'Cycles Found uses static imports between', cycles=True))

    def _format_fan_in(self) -> Dict[str, Any]:
        """Rank files by fan-in (number of other files that import them).

        High fan-in = core abstractions (base classes, shared utils).
        Zero fan-in = entry points or dead code.
        """
        if not self.analysis.graph:
            return self._build_response('fan_in_ranking', entries=[], total=0)

        top_param = self._query_params.get('top')
        top = int(top_param) if top_param else None

        graph = self._edges(LAZY_INCLUDE)
        # Union: all scanned files + files that appear as import targets (may live outside scan
        # root); every edge's target, whichever view, so a row never vanishes with &lazy.
        all_files = self._row_files(graph)
        entries = sorted(
            [
                {
                    'file': str(f),
                    'fan_in': len(graph.reverse_deps.get(f, set())),
                    'fan_out': len(graph.dependencies.get(f, set())),
                }
                for f in all_files
            ],
            key=lambda e: (-e['fan_in'], -e['fan_out'], e['file']),
        )

        total = len(entries)
        if top and top > 0:  # a negative slice would drop the tail, not cap
            entries = entries[:top]

        response = self._build_response(
            'fan_in_ranking', entries=entries, total=total,
            edge_rule=self._edge_rule(LAZY_INCLUDE, 'fan-in and fan-out count static imports between'))
        # BACK-1543: 'total' said it; the marker is what gets printed.
        note_truncation(response, 'entries', len(entries), total, 'limit', hint='raise ?top=N')
        return response

    def _format_entrypoints(self) -> Dict[str, Any]:
        """Return files with fan-in=0 — nothing imports them.

        These are unambiguously entry points (CLIs, test runners, scripts) or dead code.
        Sorted by fan-out descending: high fan-out = likely real entry point; low = likely dead code.

        BACK-1263: importers under a test root do not count toward fan-in here.
        The heuristic's own definition ("no one imports this" = "execution
        starts here") is falsified by the single most common non-caller
        importer, the test suite: a production entry point imported by its own
        tests (`from myapp.worker import main`) has fan-in > 0 and drops off
        the list, while leaf test files nothing imports flood the top sorted by
        fan-out, looking like a confident answer. Measured on a conventional
        src/ + tests/ layout: both real __main__-guarded entry points excluded,
        3 of the 4 reported were test files. A test importing a module is
        evidence that module is *testable*, not that something calls it.
        """
        if not self.analysis.graph:
            return self._build_response('entrypoints', entries=[], total_scanned=0)

        from ..utils.path_utils import is_test_path

        graph = self._edges(LAZY_INCLUDE)

        def _non_test_fan_in(f) -> int:
            return sum(
                1 for importer in graph.reverse_deps.get(f, set())
                if not is_test_path(importer)
            )

        all_files = self._row_files(graph)
        candidates = [f for f in all_files if _non_test_fan_in(f) == 0]
        entries = sorted(
            [
                {
                    'file': str(f),
                    'fan_out': len(graph.dependencies.get(f, set())),
                    # Kept visible rather than filtered out: a test file with
                    # no importers genuinely has fan-in 0, and dropping it
                    # silently would trade one wrong answer for another.
                    'is_test': is_test_path(f),
                    'test_only_importers': len(
                        graph.reverse_deps.get(f, set())
                    ),
                }
                for f in candidates
            ],
            # Non-test files first: a production entry point is what the caller
            # asked for, and previously could not appear at all.
            key=lambda e: (e['is_test'], -e['fan_out'], e['file']),
        )

        response = self._build_response(
            'entrypoints', entries=entries, total_scanned=len(all_files),
            edge_rule=self._edge_rule(LAZY_INCLUDE, 'fan-in counts static imports between',
                                      tests_counted=False),
        )
        test_share = sum(1 for e in entries if e['is_test'])
        if entries and test_share:
            meta = response.setdefault('metadata', {})
            meta.setdefault('warnings', []).append({
                'type': 'test_files_in_entrypoints',
                'message': (
                    f'{test_share} of {len(entries)} entry points are test files '
                    f'(is_test=true). Nothing imports a leaf test file, so it '
                    f'satisfies the fan-in=0 definition without being a place '
                    f'execution starts.'
                ),
            })
        return response

    def _format_components(self) -> Dict[str, Any]:
        """Score each directory as a component using import graph cohesion.

        Groups scanned files by immediate parent directory. For each directory:
        - internal: import edges where both source and target are in this directory
        - outgoing: import edges leaving this directory
        - incoming: import edges arriving from outside this directory
        - cohesion: internal / (internal + outgoing) — fraction of imports that stay local
        - top_bridge: file in this directory with most outgoing cross-boundary edges

        High cohesion = well-encapsulated component.
        Low cohesion = files import heavily outside — may not be a real component.
        """
        from collections import defaultdict

        if not self.analysis.graph:
            return self._build_response('components', components=[], total=0)

        graph = self._edges(LAZY_INCLUDE)
        # Group scanned files by immediate parent — only analyze files within the scan root
        dir_files: dict = defaultdict(set)
        for f in self.analysis.scanned_files:
            if self._in_scope(f):
                dir_files[f.parent].add(f)

        components = []
        for directory, file_set in dir_files.items():
            # BACK-1246: compare resolved (canonical, absolute) forms, not the
            # raw Path objects in file_set. Some per-language resolvers (e.g.
            # javascript.py's _resolve_target_path) return absolute dependency
            # targets while _scanned_files keeps whatever path style the CLI
            # invocation used (often relative) -- an unresolved `dep in
            # file_set` check then never matches for that language, silently
            # zeroing internal/cohesion for every component. Resolving both
            # sides here (comparison-only; `directory`/`file_set` below still
            # use the original style for display) fixes it regardless of
            # which side happens to be absolute.
            resolved_file_set = {f.resolve() for f in file_set}
            internal = 0
            outgoing = 0
            incoming = 0
            bridge_counts: dict = defaultdict(int)

            for f in file_set:
                for dep in graph.dependencies.get(f, set()):
                    if dep.resolve() in resolved_file_set:
                        internal += 1
                    else:
                        outgoing += 1
                        bridge_counts[f] += 1
                for src in graph.reverse_deps.get(f, set()):
                    if src.resolve() not in resolved_file_set:
                        incoming += 1

            total_out = internal + outgoing
            cohesion = _component_cohesion(internal, total_out, file_set)
            # BACK-1243: break ties deterministically -- max() over a dict
            # with equal-count keys otherwise depends on hash-seed-salted
            # dict iteration order (PYTHONHASHSEED), varying top_bridge
            # between runs on identical input. Sort by (count, path string)
            # so the highest count wins and ties resolve to the same file
            # every time.
            top_bridge = (
                str(max(bridge_counts.items(), key=lambda kv: (kv[1], str(kv[0])))[0])
                if bridge_counts else None
            )

            component = {
                'component': str(directory),
                'files': len(file_set),
                'internal': internal,
                'outgoing': outgoing,
                'incoming': incoming,
                **_cohesion_fields(cohesion),
                'top_bridge': top_bridge,
            }
            components.append(component)

        # Sort: measured cohesion descending (best-structured first), files descending as tiebreak.
        # A declined component has no number to rank by: it follows every measured one (never sorted as 0.00).
        components.sort(key=lambda c: (c['cohesion'] is None, -(c['cohesion'] or 0.0), -c['files'], c['component']))

        extra = {'cohesion_rule': COHESION_DECLINED_RULE} if any(c['cohesion'] is None for c in components) else {}
        return self._build_response(
            'components', components=components, total=len(components), **extra,
            edge_rule=self._edge_rule(LAZY_INCLUDE, 'internal, outgoing and incoming count static imports between'))

    def _format_external(self) -> Dict[str, Any]:
        """The package table of the imports under the path (``classify.package_table``; deps://
        computed it in its text renderer only, BACK-1054): uses per unresolved and stdlib package."""
        if not self.analysis.graph:
            return self._build_response('external_packages', external_packages=[], stdlib_packages=[],
                                        internal_imports=0, total_imports=0, total_files=0, top_importers=[])
        excluded = self._tests_excluded()
        files = {str(path): [self._format_import(stmt) for stmt in imports]
                 for path, imports in self.analysis.graph.files.items()
                 if self._in_scope(path) and not (excluded and is_test_path(path))}
        table = package_table(files, self._base_dir())
        languages = table['external_package_languages']
        return self._build_response(
            'external_packages',
            total_imports=table['total_imports'], total_files=table['total_files'],
            internal_imports=table['relative_count'],
            external_packages=[{'package': name, 'uses': uses, 'languages': languages.get(name, [])}
                               for name, uses in table['external_packages']],
            stdlib_packages=[{'package': name, 'uses': uses} for name, uses in table['stdlib_packages']],
            top_importers=[{'file': row['file'], 'imports': row['count']} for row in table['top_importers']],
        )

    def _format_unused(self) -> Dict[str, Any]:
        """Format unused imports."""
        if not self.analysis.graph:
            return {'unused': []}

        unused = [(stmt, names) for stmt, names in
                  self.analysis.graph.find_unused_imports(self.analysis.symbols_by_file)
                  if self._in_scope(stmt.file_path)]

        # `unused_names` narrows a partly-used `from x import a, b` to the names
        # actually unused (BACK-1066); `count` is statements, like `unused`.
        return self._build_response(
            'unused_imports',
            unused=[{**self._format_import(stmt), 'unused_names': names} for stmt, names in unused],
            count=len(unused)
        )

    def _format_circular(self) -> Dict[str, Any]:
        """Format circular dependency groups (one entry per SCC, not per simple path)."""
        if not self.analysis.graph:
            return {'cycles': []}

        graph = self._edges(LAZY_EXCLUDE)
        groups = self._cycle_groups(graph)
        cycle_paths = [
            [str(p) for p in graph.find_cycle_path(group)]
            for group in groups
        ]

        return self._build_response(
            'circular_dependencies',
            cycles=[[str(p) for p in group] for group in groups],
            cycle_paths=cycle_paths,
            count=len(groups),
            edge_rule=self._edge_rule(LAZY_EXCLUDE, 'cycles use static imports between', cycles=True),
        )

    def _format_violations(self) -> Dict[str, Any]:
        """Format layer violations using .reveal.yaml layer rules."""
        layer_config = load_layer_config(self._target_path)

        if layer_config is None:
            return self._build_response(
                'layer_violations',
                violations=[],
                count=0,
                note='Layer violation detection requires .reveal.yaml configuration'
            )

        project_root = self._target_path if self._target_path.is_dir() else self._target_path.parent
        violations = []

        for from_file, to_files in self._edges(LAZY_INCLUDE).dependencies.items():
            if not self._in_scope(from_file):
                continue
            for to_file in to_files:
                result = layer_config.check_import(from_file, to_file, project_root)
                if result is not None:
                    layer_name, reason = result
                    violations.append({
                        'from_file': to_posix(from_file.relative_to(project_root) if from_file.is_relative_to(project_root) else from_file),
                        'to_file': to_posix(to_file.relative_to(project_root) if to_file.is_relative_to(project_root) else to_file),
                        'layer': layer_name,
                        'reason': reason or f'{layer_name} layer violation',
                    })

        return self._build_response(
            'layer_violations',
            violations=violations,
            count=len(violations),
            edge_rule=self._edge_rule(LAZY_INCLUDE, 'violations check static imports between'),
        )

    def _scan_warnings(self) -> List[WarningEntry]:
        """A refused ?root= (the climb decided instead) and a walk the file cap cut short."""
        warnings: List[WarningEntry] = []
        if self._scan is not None and self._scan.override_rejected:
            warnings.append(cast(WarningEntry, {
                'type': 'root_rejected', 'field': 'root',
                'message': f"{self._scan.override_rejected}; resolved at the scan root the climb found instead"}))
        record = self.analysis.resolution
        if record is not None and record.capped:
            warnings.append(cast(WarningEntry, {
                'type': 'scan_capped', 'field': 'max_files', 'limit': self._scan_budget.limit,
                'message': (f"the walk kept {self._scan_budget.limit:,} source files (max_files) and stopped: "
                            "files past the cap are neither importers nor rows, so counts can under-report; "
                            "raise &max_files=N or narrow &root=")}))
        return warnings

    def _format_importers(self, importers: Any) -> Dict[str, Any]:
        """``?importers``: who imports what, from the edges every other view counts.

        A file (the requested file, or ``=FILE`` relative to the requested directory) lists each
        importer with the statement behind the edge (``resolution.ProjectResolution.edge_statements``),
        its scope and the cascade stage (via) that found it; a package-granularity language (Go)
        also counts importers of the file's directory (BACK-553). Otherwise every module under the
        path with at least one importer, with the sorted importers: the depends:// directory answer.
        """
        target = self._target_path or Path('.').resolve()
        if isinstance(importers, str):
            named, problem = self._named_importers_target(importers)
            if named is None:
                return self._build_response('importer_summary', error=problem, usage=True)
            target = named
        if target.is_file():
            return self._format_file_importers(target)
        graph = self._edges(LAZY_INCLUDE)
        entries = [
            {'file': str(f), 'fan_in': len(sources), 'importers': sorted(str(src) for src in sources)}
            for f, sources in graph.reverse_deps.items() if sources and self._in_scope(f)
            and (target == self._target_path or resolution.path_is_under(f, target))
        ]
        entries.sort(key=lambda e: (-cast(int, e['fan_in']), str(e['file'])))
        return self._build_response(
            'importer_summary', entries=entries, total=len(entries),
            edge_rule=self._edge_rule(LAZY_INCLUDE, 'importers are files whose static imports resolve here, among'))

    def _named_importers_target(self, name: str) -> Tuple[Optional[Path], str]:
        """The file or directory ``?importers=NAME`` names, or ``(None, why)``: a name that matches
        nothing is a usage error, never the directory summary (surface plan rule 9, BACK-2161).

        NAME is tried relative to the requested path and relative to the scan root; a name that
        exists under both and differs is ambiguous, and absolute paths are taken as given."""
        root = self._scan.root if self._scan else self._base_dir()
        found = _named_candidates(name, self._base_dir(), root)
        if len(found) == 1:
            return found[0], ''
        show = _path_display(self._base_dir())  # BACK-2250: the root is a host path in an error text
        if found:
            return None, (f'importers={name} is ambiguous: it names {" and ".join(str(show(str(f))) for f in found)}; '
                          f'spell the path from the scan root {show(str(root))}')
        known = {os.path.relpath(f, root): f for f in self._edges(LAZY_INCLUDE).dependencies}
        near = difflib.get_close_matches(name, [to_posix(k) for k in known], n=3, cutoff=0.5)
        hint = f'; did you mean {", ".join(near)}?' if near else ''
        return None, f'importers={name} matched no file under the scan root ({show(str(root))}){hint}'

    def _format_file_importers(self, target: Path) -> Dict[str, Any]:
        graph = self._edges(LAZY_INCLUDE)
        record = self.analysis.resolution
        statements = record.edge_statements if record is not None else {}
        rows = []
        for src, key, stmt in resolution.file_importers(graph, statements, target):
            row: Dict[str, Any] = {'file': str(src), 'line': 0, 'module': '', 'names': [], 'type': 'unknown',
                                   'is_relative': False, 'alias': None}
            if stmt is not None:
                row.update({'line': stmt.line_number, 'module': stmt.module_name, 'names': stmt.imported_names,
                            'type': stmt.import_type, 'is_relative': stmt.is_relative, 'alias': stmt.alias})
            if row['module'] and os.path.isabs(row['module']):
                row['module'] = to_posix(os.path.relpath(row['module'], self._base_dir()))
            row['scope'] = sorted(s for s in graph.edge_scopes.get(key, ()) if s) or None
            row['via'] = sorted(graph.edge_via.get(key, ())) or None
            rows.append(row)
        return self._build_response(
            'module_importers', target=str(target), importers=rows, count=len(rows),
            edge_rule=self._edge_rule(LAZY_INCLUDE, 'importers are files whose static imports resolve here, among'))

    def _get_local_names(self) -> frozenset:
        """Local package names for the scanned root, computed once (BACK-1190)."""
        if self._local_names_cache is None:
            self._local_names_cache = local_package_names(self._target_path or Path('.'))
        return self._local_names_cache

    def _get_project_namespaces(self) -> set:
        """Declared namespace/package inventory for the scanned files,
        computed once (BACK-1234) -- consulted by ``_format_import`` via
        each file's ``is_intra_project_import`` for languages that need it
        (C#/Java/Kotlin/PHP); ignored by extractors that don't."""
        if self._project_namespaces_cache is None:
            self._project_namespaces_cache = build_project_namespaces(list(self.analysis.scanned_files))
        return self._project_namespaces_cache

    def _format_import(self, stmt: ImportStatement) -> Dict[str, Any]:
        """Format single import statement for output."""
        resolved = str(stmt.resolved_path) if stmt.resolved_path else None
        # BACK-1234: only worth asking the extractor for an is_intra_project_import
        # verdict when resolution truth (above) hasn't already settled it --
        # a resolved/relative import is intra-project by definition and never
        # reaches this extra call.
        is_intra: Optional[bool] = None
        if not (stmt.is_relative or resolved):
            extractor = get_extractor(stmt.file_path)
            if extractor:
                is_intra = extractor.is_intra_project_import(
                    stmt, self._target_path or Path('.'),
                    project_namespaces=self._get_project_namespaces(),
                )
        return {
            'file': str(stmt.file_path),
            'line': stmt.line_number,
            'module': stmt.module_name,
            'names': stmt.imported_names,
            'type': stmt.import_type,
            'is_relative': stmt.is_relative,
            'alias': stmt.alias,
            # BACK-1193: real in-tree file resolve_import() resolved this import
            # to, or None if it did not resolve. None is NOT a claim the module
            # is external/stdlib — it may also be an unresolved local (missing
            # file_index coverage, monorepo/load-path boundary).
            'resolved': resolved,
            # BACK-1190: 'intra_project' | 'stdlib' | 'unresolved' | 'unknown'.
            # Classified on resolution truth (above) first; a 'stdlib' verdict
            # requires a language-appropriate list -- Python's list is never
            # used as a fallback classifier for another language (BACK-1193).
            'classification': classify_import(
                stmt.module_name, stmt.is_relative, resolved,
                family_for_path(str(stmt.file_path)), self._get_local_names(),
                is_intra=is_intra,
            ),
        }


__all__ = ['ImportsAdapter']
