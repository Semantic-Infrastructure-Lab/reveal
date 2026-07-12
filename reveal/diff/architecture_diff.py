"""Architectural diff (BACK-441): compare two structural snapshots of a tree.

``reveal architecture <path> --against <ref>``

Answers "what became structurally different between revision A and revision
B" — fan-in/fan-out shifts, introduced/resolved circular-import groups,
component-cohesion drift, complexity-centroid shift, and entry-point
churn. See internal-docs/design/ARCHITECTURAL_DIFF_DESIGN_2026-07-06.md for
the full design and the two-part (materialization / delta-logic) framing
this module implements Part B (and the Option-5 materializer) of.

Base snapshot = ``<ref>``, materialized read-only via pygit2 into a scoped
``TemporaryDirectory`` (only analyzable files are written — same filter
``find_analyzable_files`` uses). Head snapshot = the live working tree —
no materialization, the existing analysis helpers just run against ``path``
directly.

Deliberately small and self-contained: touches no other reveal module's
internals (``ImportsAdapter`` / ``AstAdapter`` / ``architecture.py``'s own
helpers are all reused unmodified). Delete this file, the ``--against`` flag
in ``architecture.py``, and this module's export in ``diff/__init__.py`` to
fully remove the feature.

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
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Same ignore-dir set find_analyzable_files() uses (reveal/adapters/diff/resolution.py)
# — kept in sync by hand since this walks a git tree, not the filesystem, so it
# can't call that function directly.
_SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv',
    'dist', 'build', '.pytest_cache', '.mypy_cache', '.tox',
    'htmlcov', '.coverage', 'eggs', '*.egg-info',
}

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
    except Exception as exc:
        logger.debug("structure extraction failed for %s: %s", path, exc)
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

    Mirrors find_analyzable_files' ignore-dir list and get_analyzer() filter
    (reveal/adapters/diff/resolution.py:187), but walks a git tree instead of
    the filesystem.
    """
    from reveal.registry import get_analyzer

    for entry in tree:
        name = entry.name
        relpath = f"{base_prefix}/{name}" if base_prefix else name
        if entry.type_str == 'tree':
            if name in _SKIP_DIRS:
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
    try:
        head_commit = repo.head.peel()
    except Exception:
        return False

    base_oid = _subtree_oid(base_commit.tree, subpath)
    head_oid = _subtree_oid(head_commit.tree, subpath)
    if base_oid is None or head_oid is None or base_oid != head_oid:
        return False

    try:
        status = repo.status()
    except Exception:
        return False

    prefix = '' if subpath in ('', '.') else subpath.rstrip('/') + '/'
    for filepath in status:
        if not prefix or filepath == subpath or filepath.startswith(prefix):
            return False
    return True


# ── Snapshot extraction (reuses architecture.py + imports.py unmodified) ───

def _is_reportable_entry_point(entry: Dict[str, Any]) -> bool:
    from reveal.cli.commands.architecture import _is_test_file

    return (
        entry.get('fan_out', 0) > 0
        and not _is_test_file(entry['file'])
        and Path(entry['file']).name != '__init__.py'
    )


def _snapshot(root: Path, top_n: int) -> Dict[str, Any]:
    """Run the import-graph + complexity analysis against `root` exactly once,
    returning the raw (absolute-path-keyed) facts needed for diffing.

    Reuses ImportsAdapter's own _format_fan_in()/_format_circular()/
    _format_components()/_format_entrypoints() (unmodified, per design doc)
    on a single adapter instance/graph build — avoids the double-parse that
    would result from also going through architecture.py's
    _run_imports_analysis() (which discards the raw per-file fan-in/out list
    building only the fan_in>0/fan_out>0 filtered views the base architecture
    report needs). Complexity still comes straight from architecture.py's
    _run_complex_functions(), unmodified.
    """
    from reveal.cli.commands.architecture import _run_complex_functions
    from reveal.adapters.imports import ImportsAdapter

    fan_in_out: List[Dict[str, Any]] = []
    circular_groups: List[List[str]] = []
    components: List[Dict[str, Any]] = []
    entry_points: List[str] = []
    unsupported_extensions: Dict[str, int] = {}

    try:
        adapter = ImportsAdapter(str(root))
        adapter._build_graph(root)
        fan_in_out = adapter._format_fan_in().get('entries', [])
        circular_groups = adapter._format_circular().get('cycles', [])
        components = adapter._format_components().get('components', [])
        raw_eps = adapter._format_entrypoints().get('entries', [])
        entry_points = [e['file'] for e in raw_eps if _is_reportable_entry_point(e)]
        unsupported_extensions = adapter.get_metadata().get('unsupported_extensions', {})
    except Exception as exc:
        logger.warning("imports analysis failed for %s: %s", root, exc)

    complex_fns = _run_complex_functions(root, top_n * 4)

    return {
        'root': root,
        'fan_in_out': fan_in_out,
        'circular_groups': circular_groups,
        'components': components,
        'entry_points': entry_points,
        'complex_fns': complex_fns,
        'unsupported_extensions': unsupported_extensions,
    }


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
    return rel.as_posix() if str(rel) != '.' else '.'


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

    component_cohesion: Dict[str, float] = {}
    for c in raw['components']:
        rel = _dir_relpath_or_none(c['component'], root)
        if rel is None:
            continue
        component_cohesion[rel] = c.get('cohesion', 0.0)

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
    base_cohesion: Dict[str, float], head_cohesion: Dict[str, float]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for component in sorted(set(base_cohesion) | set(head_cohesion)):
        base_val = base_cohesion.get(component)
        head_val = head_cohesion.get(component)
        if base_val == head_val:
            continue
        change = None if base_val is None or head_val is None else round(head_val - base_val, 3)
        out.append({
            'component': component,
            'base_cohesion': base_val,
            'head_cohesion': head_val,
            'change': change,
        })
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
        'component_coupling': _diff_components(base['component_cohesion'], head['component_cohesion']),
        'complexity_centroid': {
            'base': base_centroid,
            'head': head_centroid,
            'change': round(head_centroid - base_centroid, 2),
            'top_n': top_n,
        },
        'entry_points': _diff_entry_points(base['entry_points'], head['entry_points']),
    }


def _empty_deltas(top_n: int) -> Dict[str, Any]:
    return {
        'fan_in': [],
        'fan_out': [],
        'circular_groups': {'introduced': [], 'resolved': []},
        'component_coupling': [],
        'complexity_centroid': {'base': 0.0, 'head': 0.0, 'change': 0.0, 'top_n': top_n},
        'entry_points': {'added': [], 'removed': []},
    }


# ── Entry point ──────────────────────────────────────────────────────────────

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
    it defaults to 'HEAD' and is not itself resolved/materialized.
    """
    path = path.resolve()
    repo = _open_repo(path)
    subpath = _repo_relpath(repo, path)

    base_commit = _resolve_commit(repo, base_ref)

    deltas: Dict[str, Any]
    if _fast_exit_possible(repo, base_commit, subpath):
        deltas = _empty_deltas(top_n)
    else:
        cache = StructureCache()
        with materialize_ref(repo, base_ref, subpath, cache=cache) as base_root:
            base_raw = _snapshot(base_root, top_n)
            base_snapshot = _normalize_snapshot(base_raw, top_n)

        head_raw = _snapshot(path, top_n)
        head_snapshot = _normalize_snapshot(head_raw, top_n)

        deltas = diff_snapshots(base_snapshot, head_snapshot, top_n)

    return {
        'type': 'architecture_diff',
        'base_ref': base_ref,
        'head_ref': head_ref,
        'path': str(path),
        'deltas': deltas,
    }


def render_diff_brief(report: Dict[str, Any]) -> None:
    """Compact human-readable rendering of an architecture_diff report.

    JSON is the primary contract (design doc: "JSON-first, no verdict") —
    this is a convenience summary for terminal use, not a demand.
    """
    deltas = report['deltas']
    print(f"Architecture Diff: {report['path']}")
    print(f"  {report['base_ref']} -> {report['head_ref']}\n")

    fan_in = deltas['fan_in']
    if fan_in:
        print(f"Fan-in changes ({len(fan_in)})")
        for e in fan_in:
            print(f"  {e['file']:<54}  {e['base']} -> {e['head']}  ({_signed(e['change'])})")
        print()

    fan_out = deltas['fan_out']
    if fan_out:
        print(f"Fan-out changes ({len(fan_out)})")
        for e in fan_out:
            print(f"  {e['file']:<54}  {e['base']} -> {e['head']}  ({_signed(e['change'])})")
        print()

    cg = deltas['circular_groups']
    if cg['introduced'] or cg['resolved']:
        print("Circular groups")
        for group in cg['introduced']:
            print(f"  + introduced: {', '.join(group)}")
        for group in cg['resolved']:
            print(f"  - resolved:   {', '.join(group)}")
        print()

    coupling = deltas['component_coupling']
    if coupling:
        print(f"Component coupling changes ({len(coupling)})")
        for c in coupling:
            print(f"  {c['component']:<44}  {c['base_cohesion']} -> {c['head_cohesion']}  ({_signed(c['change'])})")
        print()

    centroid = deltas['complexity_centroid']
    print(f"Complexity centroid (top {centroid['top_n']}): {centroid['base']} -> {centroid['head']}  ({_signed(centroid['change'])})")

    eps = deltas['entry_points']
    if eps['added'] or eps['removed']:
        print("\nEntry points")
        for f in eps['added']:
            print(f"  + {f}")
        for f in eps['removed']:
            print(f"  - {f}")


def _signed(value: Optional[float]) -> str:
    if value is None:
        return 'n/a'
    return f"+{value}" if value > 0 else str(value)


__all__ = [
    'StructureCache',
    'materialize_ref',
    'diff_snapshots',
    'run_architecture_diff',
    'render_diff_brief',
]
