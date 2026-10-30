"""Architectural diff (BACK-441): compare two structural snapshots of a tree.

``reveal architecture <path> --against <ref>``

Answers "what became structurally different between revision A and revision
B" — fan-in/fan-out shifts, introduced/resolved circular-import groups,
component-cohesion drift, complexity-centroid shift, and entry-point
churn. This module implements Part B (and the Option-5 materializer) of the
two-part (materialization / delta-logic) design.

Base snapshot = ``<ref>``, materialized read-only via pygit2 into a scoped
``TemporaryDirectory`` (only analyzable files are written — same filter
``find_analyzable_files`` uses). Head snapshot = the live working tree —
no materialization, the existing analysis helpers just run against ``path``
directly.

Deliberately small and self-contained: touches no other reveal module's
internals: import analysis and domain projections use their public owners;
complexity composes the existing AST query. Both public comparison spellings
reuse this engine and its snapshot evidence.

Divergences from the design doc's stated ideal, and why (see also the
module's own docstrings below):

* **OID memoization** (design doc "performance nuance" section) asks to
  memoize per-file parse/structure extraction by blob OID so a file whose
  content is unchanged between the two refs isn't re-parsed. That saving can
  only be realized by hooking into ``ImportsAdapter``/``AstAdapter``'s own
  per-file walk — which the design doc itself rules out ("Zero changes to
  ImportsAdapter / AstAdapter"). ``StructureCache`` below implements the
  memoization contract correctly and is unit-tested in isolation, but it is
  *not* wired into the hot path of the reused adapters, so it does not
  actually save a repeat parse in the default `--against` flow today. It is
  used for the one legitimate saving available without touching those
  adapters: dedup within a single tree walk when the same blob OID recurs at
  multiple paths (e.g. duplicate boilerplate files). Full cross-ref reuse
  needs BACK-486's virtual file-map (already scoped as separate, later work).
* **Fast-exit on unchanged subtree OID** is only attempted for the common
  "working tree exactly matches HEAD, and HEAD's subtree OID for the target
  path equals the base ref's" case (via ``repo.status()`` — cheap and
  read-only). A fully general fast-exit against an arbitrary dirty working
  tree would require hashing every file, which defeats the point of a
  fast-exit; the design doc explicitly allows skipping this for the
  working-tree case ("use your judgment").
"""

from __future__ import annotations

import logging
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, cast

from ..defaults import (
    AMBIGUOUS_SKIP_DIRECTORIES, SKIP_DIRECTORIES, VENV_DIR_NAMES, VENV_MARKERS,
)

from ..reveal_types import ErrorEntry, RevealMeta, WarningEntry
from ..adapters.base import ResourceAdapter
from ..utils.entry_points import active_entry_points

logger = logging.getLogger(__name__)


def _is_skippable_tree_entry(repo, entry) -> bool:
    """Git-tree analog of ``reveal.utils.path_utils.is_noise_dir``, read from the tree
    itself rather than ``os.scandir``, since this walk is over a ref, not the filesystem.

    Same rules: SKIP_DIRECTORIES and ``*.egg-info`` always skip; ``env``/``venv`` skip only
    when they are a virtualenv (a marker at their top, BACK-1582); ``build``/``dist`` only
    when no source file sits directly inside (BACK-552).
    """
    name = entry.name
    if name in SKIP_DIRECTORIES or name.endswith('.egg-info'):
        return True
    if name not in AMBIGUOUS_SKIP_DIRECTORIES:
        return False
    subtree = repo[entry.id]
    if name in VENV_DIR_NAMES:
        return any(_tree_has(subtree, marker) for marker in VENV_MARKERS)
    from ..registry import get_code_extensions
    code_exts = get_code_extensions()
    for child in subtree:
        if child.type_str == 'blob' and Path(child.name).suffix.lower() in code_exts:
            return False
    return True


def _tree_has(tree, path: str) -> bool:
    try:
        tree[path]
    except KeyError:
        return False
    return True


_DEFAULT_COMPLEXITY_TOP_N = 20


# ── OID-memoized structure extraction ───────────────────────────────────────

def _extract_structure(path: Path) -> Dict[str, Any]:
    """Parse one file's structure via the registered analyzer. Pure function
    of file content — safe to memoize by blob OID (see StructureCache)."""
    from reveal.registry import get_analyzer

    analyzer_class = get_analyzer(str(path), allow_fallback=False)
    if not analyzer_class:
        return {}
    try:
        return analyzer_class(str(path)).get_structure()
    except Exception as exc:  # boundary-ok: broad-except -- an analyzer is arbitrary per-language code; the failure is logged at warning and the file contributes an empty structure
        logger.warning("structure extraction failed for %s: %s", path, exc)
        return {}


class StructureCache:
    """Memoizes per-file structure extraction, keyed by git blob OID.

    Parsing is a pure function of content, so two paths sharing a blob OID
    never need to be parsed twice. Never used as a cache for *derived* graph
    metrics (fan-in/out, SCC, cohesion, complexity) — those depend on the
    whole-tree edge set, not just a file's own content, and must always be
    recomputed fresh per snapshot (see module docstring's performance-nuance
    note and the design doc section it references).
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    def get_structure(self, path: Path, oid: str) -> Dict[str, Any]:
        cached = self._cache.get(oid)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        structure = _extract_structure(path)
        self._cache[oid] = structure
        return structure


# ── Materialization (Part A: pygit2 -> scoped TemporaryDirectory) ──────────

def _open_repo(path: Path):
    import pygit2

    repo_path = pygit2.discover_repository(str(path))
    if not repo_path:
        raise ValueError(f"Not a git repository: {path}")
    return pygit2.Repository(repo_path)


def _repo_root(repo) -> Path:
    root = repo.workdir or repo.path
    return Path(root).resolve()


def _repo_relpath(repo, path: Path) -> str:
    """`path` expressed relative to the repo root, posix-separated."""
    rel = path.resolve().relative_to(_repo_root(repo))
    return rel.as_posix()


def _resolve_commit(repo, ref: str):
    import pygit2

    try:
        obj = repo.revparse_single(ref)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Cannot resolve ref: {ref}") from exc
    while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
        obj = obj.peel(pygit2.Commit)
    if not isinstance(obj, pygit2.Commit):
        raise ValueError(f"Cannot resolve ref to a commit: {ref}")
    return obj


def _subtree_oid(tree, subpath: str) -> Optional[str]:
    """OID of the tree/blob entry at `subpath` within `tree`, or None if absent."""
    if not subpath or subpath == '.':
        return str(tree.id)
    try:
        return str(tree[subpath].id)
    except KeyError:
        return None


def _iter_analyzable_blobs(repo, tree, base_prefix: str = '') -> Iterator[Tuple[str, Any]]:
    """Yield (relpath, blob) for every analyzable blob under `tree`, recursively.

    Mirrors find_analyzable_files' ignore-dir logic and get_analyzer() filter
    (reveal/adapters/diff/resolution.py:187), but walks a git tree instead of
    the filesystem (see _is_skippable_tree_entry).
    """
    from reveal.registry import get_analyzer

    for entry in tree:
        name = entry.name
        relpath = f"{base_prefix}/{name}" if base_prefix else name
        if entry.type_str == 'tree':
            if _is_skippable_tree_entry(repo, entry):
                continue
            yield from _iter_analyzable_blobs(repo, repo[entry.id], relpath)
        elif entry.type_str == 'blob':
            if get_analyzer(relpath, allow_fallback=False):
                yield relpath, repo[entry.id]


@contextmanager
def materialize_ref(repo, ref: str, subpath: str, cache: Optional[StructureCache] = None):
    """Materialize the analyzable files under `subpath` at `ref` into a scoped
    read-only TemporaryDirectory, preserving relative paths.

    Yields the temp root Path — same shape as the live `subpath` directory,
    so the existing architecture-command helpers can point straight at it.
    Cleaned up unconditionally (context manager) even on exception.
    """
    commit = _resolve_commit(repo, ref)
    tree = commit.tree

    if subpath in ('', '.'):
        scoped_tree = tree
    else:
        try:
            entry = tree[subpath]
        except KeyError:
            raise ValueError(f"Path '{subpath}' not found at ref '{ref}'")
        if entry.type_str != 'tree':
            raise ValueError(f"Path '{subpath}' at ref '{ref}' is not a directory")
        scoped_tree = repo[entry.id]

    with tempfile.TemporaryDirectory(prefix='reveal-archdiff-') as tmp:
        tmp_root = Path(tmp)
        seen_oids: Set[str] = set()
        for relpath, blob in _iter_analyzable_blobs(repo, scoped_tree):
            dest = tmp_root / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob.data)
            oid = str(blob.id)
            if cache is not None and oid not in seen_oids:
                seen_oids.add(oid)
                # Dedup within this single materialization pass: if the same
                # blob OID recurs at another path (duplicate content), its
                # structure is parsed once and reused — see StructureCache.
                cache.get_structure(dest, oid)
        yield tmp_root


def _fast_exit_possible(repo, base_commit, subpath: str) -> bool:
    """True only if the live working tree is provably identical, under
    `subpath`, to `base_commit`'s tree — i.e. HEAD == base_commit's subtree
    OID *and* there are no uncommitted changes touching `subpath`.

    Deliberately conservative (see module docstring): a general fast-exit
    against an arbitrary dirty working tree would require hashing every
    file, defeating the purpose.
    """
    import pygit2
    try:
        head_commit = repo.head.peel()
    except (pygit2.GitError, KeyError):  # unborn or detached-and-missing HEAD: run the full diff
        return False

    base_oid = _subtree_oid(base_commit.tree, subpath)
    head_oid = _subtree_oid(head_commit.tree, subpath)
    if base_oid is None or head_oid is None or base_oid != head_oid:
        return False

    try:
        from ..utils.gitignore import gitignore_enabled
        status = repo.status(ignored=not gitignore_enabled())
    except pygit2.GitError:
        return False

    prefix = '' if subpath in ('', '.') else subpath.rstrip('/') + '/'
    for filepath in status:
        if not prefix or filepath == subpath or filepath.startswith(prefix):
            return False
    return True


# ── Snapshot extraction (reuses the existing imports and AST owners) ──────

def _ast_row_valid(row: Any) -> bool:
    return (isinstance(row, dict)
            and all(isinstance(row.get(key), str) and bool(row[key]) for key in ('file', 'name'))
            and type(row.get('complexity')) is int and row['complexity'] >= 0)


def _ast_counts_valid(data: Dict[str, Any], rows: list) -> bool:
    return (all(type(data.get(key)) is int and data[key] >= 0
                for key in ('total_files', 'total_results', 'displayed_results'))
            and data['displayed_results'] == len(rows)
            and data['total_results'] >= data['displayed_results'])


def _capture_ast_observations(data: Any, observations: Optional[Dict[str, bool]]) -> None:
    if observations is None:
        return
    rows = data.get('results', data.get('elements')) if isinstance(data, dict) else None
    valid = (isinstance(data, dict) and not data.get('error') and isinstance(rows, list)
             and all(_ast_row_valid(row) for row in rows) and _ast_counts_valid(data, rows))
    if not valid:
        observations['failed'] = True
    elif data['total_results'] > 0:
        # The existing domain-filtered count precedes the limit, including zero.
        # At limit=0 the producer is authoritative for the hidden identities.
        observations['usable'] = True


def _run_complex_functions(adapter: 'ResourceAdapter', path: Path, limit: int, *,
                           observations: Optional[Dict[str, bool]] = None) -> List[Dict[str, Any]]:
    if observations is None:
        observations = getattr(adapter, '_architecture_observations', None)
    from reveal.adapters.ast import AstAdapter
    data = adapter.compose(AstAdapter, str(path), default={},
                            query=f'complexity>9&sort=-complexity&limit={limit}',
                            cut_as=('complex_functions', 'raise ?top=N'))
    _capture_ast_observations(data, observations)
    return data.get('results', data.get('elements', []))

def _snapshot(root: Path, top_n: int) -> Dict[str, Any]:
    """Run the import-graph + complexity analysis against `root` exactly once,
    returning the raw (absolute-path-keyed) facts needed for diffing.

    Reuses the shared ImportView domain projections over one service build — avoids the double-parse that
    would result from also going through architecture.py's
    _run_imports_analysis() (which discards the raw per-file fan-in/out list
    building only the fan_in>0/fan_out>0 filtered views the base architecture
    report needs). Complexity uses the same AST composition query and cut.
    The existing adapter shells own metadata only; neither shell runs analysis.
    """
    from reveal.adapters.ast import AstAdapter
    from reveal.analyzers.imports.views import ImportView
    from reveal.analyzers.imports.diagnostics import integrity_warnings
    from reveal.analyzers.imports.resolution import ScanRoot
    from reveal.analyzers.imports import service as import_analysis

    fan_in_out: List[Dict[str, Any]] = []
    circular_groups: List[List[str]] = []
    components: List[Dict[str, Any]] = []
    entry_points: List[str] = []
    unsupported_extensions: Dict[str, int] = {}
    edge_rules: Dict[str, Any] = {}
    owner = AstAdapter(str(root))
    imports_state = 'complete'

    try:
        built = import_analysis.analyze(import_analysis.path_scope(root))
        adapter = ImportView(built.analysis, root, ScanRoot(root, 'path'), import_analysis.DEFAULT_FILE_CAP)
        with import_analysis.composed_rules('architecture://'):  # BACK-2087
            fan_in_data = adapter.fan_in()
            circular_data = adapter.circular()
            components_data = adapter.components()
            entrypoints_data = adapter.entrypoints()
        fan_in_out = fan_in_data.get('entries', [])
        circular_groups = circular_data.get('cycles', [])
        components = components_data.get('components', [])
        raw_eps = entrypoints_data.get('entries', [])
        edge_rules = import_analysis.architecture_edge_rules(
            fan_in_data, entrypoints_data, components_data, circular_data)  # BACK-2087
        entry_points = [e['file'] for e in active_entry_points(raw_eps)]
        metadata = adapter.get_metadata()
        unsupported_extensions = metadata.get('unsupported_extensions', {})
        owner.fold_meta({'warnings': integrity_warnings(built.analysis, root)})
        if (adapter.analysis.files_failed or adapter.analysis.files_lost
                or bool(getattr(adapter.analysis.graph, 'traversal_failures', ()))):
            imports_state = 'incomplete'
    except Exception as exc:  # boundary-ok: broad-except -- whole-tree import analysis runs arbitrary analyzers; retain the attributed failure and reject comparison rather than treating empty facts as evidence
        owner.record_composed_error('ImportsAdapter', root, exc)
        imports_state = 'failed'

    complexity_owner = AstAdapter(str(root))
    try:
        complex_fns = _run_complex_functions(complexity_owner, root, top_n * 4)
    except Exception as exc:  # boundary-ok: broad-except -- the existing child helper postprocesses arbitrary analyzer output outside compose; retain any failure at this required component boundary
        complexity_owner.record_composed_error('AstAdapter', root, exc)
        complex_fns = []
    complexity_meta = cast(Dict[str, Any], complexity_owner.composed_meta() or {})
    complexity_state = _complexity_state(complexity_meta)
    for kind in ('warnings', 'errors'):
        if kind in complexity_meta:
            complexity_meta[kind] = [dict(entry, component='complexity') for entry in complexity_meta[kind]]
    owner.fold_meta(cast(RevealMeta, complexity_meta))

    return {
        'root': root,
        'completeness': {'imports': imports_state, 'complexity': complexity_state},
        'meta': owner.composed_meta(),
        'fan_in_out': fan_in_out,
        'circular_groups': circular_groups,
        'components': components,
        'entry_points': entry_points,
        'complex_fns': complex_fns,
        'unsupported_extensions': unsupported_extensions,
        'edge_rules': edge_rules,
    }


def _complexity_state(meta: Dict[str, Any]) -> str:
    if meta.get('errors'):
        return 'failed'
    missing = {'analysis_failed', 'parse_recovered'}
    if any(w.get('type') in missing for w in meta.get('warnings', [])):
        return 'incomplete'
    return 'complete'


def _relpath_or_none(file_str: str, root: Path) -> Optional[str]:
    try:
        return Path(file_str).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # Import edge resolved to a file outside the diff target root —
        # not part of what we're diffing, per "path normalization" (edge case 3).
        return None


def _dir_relpath_or_none(dir_str: str, root: Path) -> Optional[str]:
    try:
        rel = Path(dir_str).resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return rel.as_posix() if str(rel) != '.' else '.'  # noqa: V026 -- compares against '.', never rendered


def _component_cohesion(components: List[Dict[str, Any]], root: Path) -> Tuple[Dict[str, float], Set[str]]:
    """Cohesion per component directory, and the directories whose cohesion is declined (same-package-visibility
    language, BACK-1428): a declined value is not a number and never 0.0."""
    cohesion: Dict[str, float] = {}
    declined: Set[str] = set()
    for c in components:
        rel = _dir_relpath_or_none(c['component'], root)
        if rel is None:
            continue
        if c.get('cohesion') is None and c.get('cohesion_reason'):
            declined.add(rel)
            continue
        cohesion[rel] = c.get('cohesion', 0.0)
    return cohesion, declined


def _normalize_snapshot(raw: Dict[str, Any], top_n: int) -> Dict[str, Any]:
    root: Path = raw['root']

    fan_in: Dict[str, int] = {}
    fan_out: Dict[str, int] = {}
    for e in raw['fan_in_out']:
        rel = _relpath_or_none(e['file'], root)
        if rel is None:
            continue
        fan_in[rel] = e.get('fan_in', 0)
        fan_out[rel] = e.get('fan_out', 0)

    circular_groups: List[frozenset] = []
    for group in raw['circular_groups']:
        rels = [r for r in (_relpath_or_none(f, root) for f in group) if r is not None]
        if rels:
            circular_groups.append(frozenset(rels))

    component_cohesion, component_declined = _component_cohesion(raw['components'], root)

    entry_points: Set[str] = {
        rel for rel in (_relpath_or_none(f, root) for f in raw['entry_points']) if rel is not None
    }

    top_fns = raw['complex_fns'][:top_n]
    complexities = [fn.get('complexity', 0) for fn in top_fns]
    centroid = round(sum(complexities) / len(complexities), 2) if complexities else 0.0

    return {
        'fan_in': fan_in,
        'fan_out': fan_out,
        'circular_groups': circular_groups,
        'component_cohesion': component_cohesion,
        'component_declined': component_declined,
        'entry_points': entry_points,
        'complexity_centroid': centroid,
        'unsupported_extensions': raw['unsupported_extensions'],
    }


# ── Part B: the delta logic ─────────────────────────────────────────────────

def _diff_counts(base: Dict[str, int], head: Dict[str, int], key: str) -> List[Dict[str, Any]]:
    """Diff a {relpath: count} map from each side into the fan_in/fan_out
    delta-list shape. Absent side is `null`, never `0` (edge case #1) —
    added/removed files must be distinguishable from "existed with count 0".
    Only files with an actual delta (added, removed, or a changed count) are
    included; unchanged files (same count on both sides, or absent on both)
    are omitted as noise.
    """
    out: List[Dict[str, Any]] = []
    for relpath in sorted(set(base) | set(head)):
        base_val = base.get(relpath)
        head_val = head.get(relpath)
        if base_val == head_val:
            continue
        change = None if base_val is None or head_val is None else head_val - base_val
        out.append({
            'file': relpath,
            'base': base_val,
            'head': head_val,
            'change': change,
        })
    return out


def _diff_circular_groups(base_groups: List[frozenset], head_groups: List[frozenset]) -> Dict[str, Any]:
    base_set = set(base_groups)
    head_set = set(head_groups)
    introduced = sorted((sorted(g) for g in head_set - base_set), key=lambda g: (len(g), g))
    resolved = sorted((sorted(g) for g in base_set - head_set), key=lambda g: (len(g), g))
    return {'introduced': introduced, 'resolved': resolved}


def _diff_components(
    base_cohesion: Dict[str, float], head_cohesion: Dict[str, float],
    base_declined: Optional[Set[str]] = None, head_declined: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Cohesion deltas per component. A component whose cohesion is declined (same-package-visibility
    language, BACK-1428) has no number: declined on both sides is no delta, declined on one side is
    reported as such (``declined_on``), never as a move to or from 0.0 or as an added/removed component."""
    base_declined = base_declined or set()
    head_declined = head_declined or set()
    out: List[Dict[str, Any]] = []
    for component in sorted(set(base_cohesion) | set(head_cohesion) | base_declined | head_declined):
        base_val = base_cohesion.get(component)
        head_val = head_cohesion.get(component)
        if base_val == head_val:  # includes declined on both sides, or declined against absent
            continue
        change = None if base_val is None or head_val is None else round(head_val - base_val, 3)
        entry = {
            'component': component,
            'base_cohesion': base_val,
            'head_cohesion': head_val,
            'change': change,
        }
        if component in base_declined:
            entry['declined_on'] = 'base'
        elif component in head_declined:
            entry['declined_on'] = 'head'
        out.append(entry)
    return out


def _diff_entry_points(base_eps: Set[str], head_eps: Set[str]) -> Dict[str, List[str]]:
    return {
        'added': sorted(head_eps - base_eps),
        'removed': sorted(base_eps - head_eps),
    }


def diff_snapshots(base: Dict[str, Any], head: Dict[str, Any], top_n: int) -> Dict[str, Any]:
    """Pure diff of two normalized snapshots (see _normalize_snapshot) into
    the architecture_diff output contract's `deltas` object. No I/O, no git —
    exercised directly by unit tests independent of the CLI/materialization.
    """
    base_centroid = base['complexity_centroid']
    head_centroid = head['complexity_centroid']

    return {
        'fan_in': _diff_counts(base['fan_in'], head['fan_in'], 'fan_in'),
        'fan_out': _diff_counts(base['fan_out'], head['fan_out'], 'fan_out'),
        'circular_groups': _diff_circular_groups(base['circular_groups'], head['circular_groups']),
        'component_coupling': _diff_components(
            base['component_cohesion'], head['component_cohesion'],
            base.get('component_declined'), head.get('component_declined')),
        'complexity_centroid': {
            'base': base_centroid,
            'head': head_centroid,
            'change': round(head_centroid - base_centroid, 2),
            'top_n': top_n,
        },
        'entry_points': _diff_entry_points(base['entry_points'], head['entry_points']),
    }


def _empty_deltas(top_n: int) -> Dict[str, Any]:
    """Zero change proved by tree identity, without measured snapshot values."""
    return {
        'fan_in': [],
        'fan_out': [],
        'circular_groups': {'introduced': [], 'resolved': []},
        'component_coupling': [],
        'complexity_centroid': {'base': None, 'head': None, 'change': 0.0, 'top_n': top_n},
        'entry_points': {'added': [], 'removed': []},
    }


# ── Entry point ──────────────────────────────────────────────────────────────

def _comparison_snapshot_proof(analysis) -> bool:
    snapshots = analysis.get('snapshots')
    if analysis.get('basis') == 'identical_tree':
        return analysis['complete'] is True and snapshots == {}
    if (analysis.get('basis') != 'snapshots' or not isinstance(snapshots, dict)
            or set(snapshots) != {'base', 'head'}):
        return False
    states: List[str] = []
    for components in snapshots.values():
        if not isinstance(components, dict) or set(components) != {'imports', 'complexity'}:
            return False
        states.extend(components.values())
    return (all(state in ('complete', 'incomplete', 'failed') for state in states)
            and analysis['complete'] is all(state == 'complete' for state in states))


def comparison_answer_requirement_error(result, prior_facts=None) -> Optional[str]:
    """Require comparison proof, allowing an attributed rejection before analysis."""
    from ..utils.results import AnalysisCompleteness, FailureCause
    analysis = result.get('analysis')
    if (isinstance(analysis, dict) and isinstance(analysis.get('complete'), bool)
            and _comparison_snapshot_proof(analysis)):
        return None
    errors = result.get('meta', {}).get('errors', [])
    invalid_only = bool(errors) and all(error.get('code') == 'invalid_request' for error in errors)
    before_analysis = prior_facts is None or (
        prior_facts.completeness is AnalysisCompleteness.NOT_STARTED
        and prior_facts.failures == frozenset({FailureCause.INVALID_REQUEST}))
    if invalid_only and 'analysis' not in result and before_analysis:
        return None
    return 'Architecture comparison missing required completeness evidence'


def _comparison_completeness(result, meta, invalid_only):
    from ..utils.results import AnalysisCompleteness
    errors = meta.get('errors', [])
    missing = {'analysis_failed', 'parse_recovered', 'partial_parse', 'worker_lost', 'analysis_incomplete'}
    missing_inputs = any(w.get('type') in missing for w in meta.get('warnings', []))
    if any(error.get('code') == 'E_ARCHITECTURE_ANALYSIS' for error in errors):
        return AnalysisCompleteness.FAILED
    if invalid_only and 'analysis' not in result and not missing_inputs:
        return AnalysisCompleteness.NOT_STARTED
    analysis = result.get('analysis') if isinstance(result, dict) else None
    complete = isinstance(analysis, dict) and analysis.get('complete') is True
    incomplete = (bool(errors) and not invalid_only) or missing_inputs or not complete
    return AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE


def comparison_execution_facts(result):
    """Classify required comparison evidence independently of its public result type."""
    from ..utils.results import (ExecutionFacts, FailureCause, failure_execution_facts,
                                 result_execution_facts)
    meta = result.get('meta', {}) if isinstance(result, dict) else {}
    errors = meta.get('errors', [])
    invalid_only = bool(errors) and all(error.get('code') == 'invalid_request' for error in errors)
    state = _comparison_completeness(result, meta, invalid_only)
    cause = FailureCause.INVALID_REQUEST if invalid_only else FailureCause.ANALYSIS
    facts = result_execution_facts(result, completeness=state, failure_cause=cause)
    if invalid_only and not facts.failures:
        return ExecutionFacts(state, failures=failure_execution_facts(cause).failures)
    return facts


def run_architecture_diff(
    path: Path,
    base_ref: str,
    head_ref: str = 'HEAD',
    top_n: int = _DEFAULT_COMPLEXITY_TOP_N,
) -> Dict[str, Any]:
    """Diff `path`'s architecture between `base_ref` and the live working
    tree, returning the architecture_diff output contract.

    `head_ref` is a display label only (the live working tree is always the
    head snapshot per BACK-441's chosen flag shape — see module docstring);
    it defaults to 'HEAD' and is not itself resolved/materialized. The report names
    ``path`` as the caller spelled it (BACK-2282).
    """
    spelling = path
    path = path.resolve()
    repo = _open_repo(path)
    subpath = _repo_relpath(repo, path)

    base_commit = _resolve_commit(repo, base_ref)

    if _fast_exit_possible(repo, base_commit, subpath):
        return _comparison_report(path, base_ref, head_ref, _empty_deltas(top_n),
                                  {'complete': True, 'basis': 'identical_tree', 'snapshots': {}}, [],
                                  spelling=spelling)

    from ..utils.exclusions import remapped_exclusion_scope
    from ..utils.gitignore import gitignore_scope
    cache = StructureCache()
    with materialize_ref(repo, base_ref, subpath, cache=cache) as base_root:
        with remapped_exclusion_scope(path, base_root), gitignore_scope(False):
            base_raw = _snapshot(base_root, top_n)
        base_snapshot = _normalize_snapshot(base_raw, top_n)
        base_meta = _snapshot_meta(base_raw, 'base')

    head_raw = _snapshot(path, top_n)
    head_snapshot = _normalize_snapshot(head_raw, top_n)
    states = {'base': base_raw['completeness'], 'head': head_raw['completeness']}
    complete = all(state == 'complete' for components in states.values() for state in components.values())
    analysis = {'complete': complete, 'basis': 'snapshots', 'snapshots': states,
                'unsupported_extensions': {'base': base_raw['unsupported_extensions'],
                                           'head': head_raw['unsupported_extensions']}}
    confidences = {side: (raw.get('meta') or {}).get('confidence')
                   for side, raw in (('base', base_raw), ('head', head_raw))}
    analysis['confidence'] = confidences
    supplied = [value for value in confidences.values() if value is not None]
    confidence = min(supplied) if supplied else None
    deltas = diff_snapshots(base_snapshot, head_snapshot, top_n) if complete else None
    # Both sides are counted by one rule (the same formatters and defaults), so the answer states it once.
    return _comparison_report(path, base_ref, head_ref, deltas, analysis,
                              [*base_meta, *_snapshot_meta(head_raw, 'head')], confidence=confidence,
                              edge_rules=head_raw['edge_rules'] if deltas is not None else None,
                              spelling=spelling)


def _diagnostic_path(value: str, root: Path) -> str:
    from ..utils.path_utils import to_posix
    displayed, prefix = to_posix(value), to_posix(root).rstrip('/')
    if displayed == prefix:
        return '.'
    return displayed[len(prefix) + 1:] if displayed.startswith(prefix + '/') else displayed


def _diagnostic_message(message: str, root: Path) -> str:
    from ..utils.path_utils import to_posix
    spellings = {str(root), to_posix(root), repr(root), repr(str(root))[1:-1]}
    for spelling in sorted(spellings, key=len, reverse=True):
        pattern = r"(?<![\w/\\.-])" + re.escape(spelling) + r"(?=$|[\s/\\'\"),;:])"
        message = re.sub(pattern, '.', message)
    return message


def _snapshot_meta(raw: Dict[str, Any], side: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Attribute diagnostics and remove known materialization path spellings."""
    root = raw['root']
    entries = []
    for kind in ('warnings', 'errors'):
        for entry in (raw.get('meta') or {}).get(kind, []):
            entry = dict(entry, snapshot=side, component=entry.get('component', 'imports'))
            if entry.get('file'):
                entry['file'] = _diagnostic_path(entry['file'], root)
            if entry.get('files'):
                entry['files'] = [_diagnostic_path(file, root) for file in entry['files']]
            if entry.get('causes'):
                entry['causes'] = [_diagnostic_message(cause, root) for cause in entry['causes']]
            entry['message'] = f"{side}: {_diagnostic_message(entry.get('message', ''), root)}"
            entries.append((kind, entry))
    return entries


def _comparison_report(path: Path, base_ref: str, head_ref: str, deltas: Optional[Dict[str, Any]],
                       analysis: Dict[str, Any], diagnostics: List[Tuple[str, Dict[str, Any]]],
                       *, confidence: Optional[float] = None,
                       edge_rules: Optional[Dict[str, Any]] = None,
                       spelling: Optional[Path] = None) -> Dict[str, Any]:
    from ..utils.results import ResultBuilder
    from ..utils.path_utils import as_spelled
    from ..reveal_types import CONTRACT_VERSION
    shown = as_spelled(path, spelling if spelling is not None else path)
    data = {'base_ref': base_ref, 'head_ref': head_ref, 'path': shown,
            'deltas': deltas, 'analysis': analysis, **(edge_rules or {})}
    if not analysis['complete']:
        data['error'] = 'Architecture comparison unavailable: required snapshot evidence is incomplete'
    return cast(Dict[str, Any], ResultBuilder.create(
        result_type='architecture_diff', source=shown, data=data, contract_version=CONTRACT_VERSION,
        warnings=cast(List[WarningEntry], [entry for kind, entry in diagnostics if kind == 'warnings']) or None,
        errors=cast(List[ErrorEntry], [entry for kind, entry in diagnostics if kind == 'errors']) or None,
        confidence=confidence,
    ))


def render_diff_brief(report: Dict[str, Any]) -> None:
    """Compatibility printer; the rendering owner returns the shared text body."""
    from ..rendering.diff import architecture_diff_text
    print(architecture_diff_text(report), end='')


__all__ = [
    'comparison_answer_requirement_error',
    'comparison_execution_facts',
    'StructureCache',
    'materialize_ref',
    'diff_snapshots',
    'run_architecture_diff',
    'render_diff_brief',
]
