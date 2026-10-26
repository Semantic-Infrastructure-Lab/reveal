"""pack:// adapter - token-budgeted context snapshot for LLM consumption.

Scan/rank logic lives here; presentation lives in rendering/adapters/pack.py.
The CLI command, pack:// and the reveal_pack MCP tool all run through the declared
execution path.
"""

import io
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Sequence, Set, Tuple

from reveal.reveal_types import CONTRACT_VERSION
from reveal.registry import get_code_extensions

from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.imports import service as import_analysis
from ..analyzers.imports.types import LAZY_INCLUDE
from ..conventions import conventions_for_path
from ..rendering.adapters.pack import PackRenderer
from ..utils.path_utils import (
    DISPLAY,
    _walk_code_files,
    classify_path_provenance,
    to_posix,
    traversal_failed_warning,
    failure_of,
)
from ..utils.query_binding import bind_declared_params
from ..utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec, param_schema,
                                  split_exclude_param)
from ..utils.results import AnalysisCompleteness, ResultBuilder, result_execution_facts
from reveal.utils.lines import split_lines

logger = logging.getLogger(__name__)

# Entry point filename patterns (highest priority) live per language in
# conventions.LanguageConventions.entry_point_files (BACK-1287).
# __init__.py excluded from unconditional entry points — most are near-empty;
# only promote them if they have substantial content (scored by size below)

# BACK-1196: config/build files are ONE PER PROJECT, not a resolution/routing
# convention repeated across a tree the way 'index.js'/'main.py' are (a
# monorepo can have hundreds of near-empty index.js barrel files — Discourse
# scored 27 of them into an 8K-budget pack, ZERO substantive application
# code). These always keep the full entry-point bonus regardless of size —
# a small package.json/Cargo.toml is still a unique, legitimate signal.
_ENTRY_POINT_CONFIG_FILES = {
    'makefile', 'dockerfile', 'pyproject.toml', 'package.json', 'cargo.toml',
    'go.mod', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'gemfile',
    'composer.json', 'cmakelists.txt', 'package.swift',
}


def _is_entry_config_file(name: str) -> bool:
    """Project manifest/build file (matched case-insensitively -- BACK-1287 fixed
    'Makefile'/'Dockerfile' never matching the lowercased name)."""
    lower = name.lower()
    return lower in _ENTRY_POINT_CONFIG_FILES or lower.endswith('.csproj')


def _is_entry_point_name(name: str) -> bool:
    """Convention-based entry-point basename for the file's own language."""
    lower = name.lower()
    return lower in conventions_for_path(lower).entry_point_files

_APPROX_CHARS_PER_TOKEN = 4

# Whole-component key directory/stem names that indicate architectural importance.
# Matched against path segments only (not substrings) to avoid false positives
# like 'main' inside 'maintainability' or 'core' inside 'decorator'.
_KEY_DIR_SEGMENTS = {'main', 'core', 'api', 'routes', 'models', 'schema', 'auth', 'config'}

# Non-source data/markup extensions (BACK-526): supporting material, not
# "key modules" of the codebase's logic. Penalized in _compute_priority so a
# data blob sitting in a key-named directory can't masquerade as a core module.
_DATA_MARKUP_EXTENSIONS = {
    '.json', '.yaml', '.yml', '.csv', '.md', '.html', '.css', '.scss', '.sql', '.toml',
}


def _get_changed_files(path: Path, since_ref: str) -> Tuple[Set[str], Optional[str]]:
    """Return absolute paths of files changed since *since_ref* via git diff.

    Uses ``git diff --name-only <ref>...HEAD`` (triple-dot = since branch point).
    Returns (set_of_abs_paths, error_message_or_None).
    """
    # Find git root (may be above path)
    try:
        root_result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, cwd=str(path.parent if path.is_file() else path), timeout=10, encoding='utf-8', errors='replace',
        )
        if root_result.returncode != 0:
            return set(), "not a git repository"
        git_root = Path(root_result.stdout.strip())
    except FileNotFoundError:
        return set(), "git not found"
    except subprocess.TimeoutExpired:
        return set(), "git rev-parse timed out"

    try:
        # --end-of-options: since_ref is caller-controlled (MCP reveal_pack's `since`
        # param) -- without it, a ref starting with '-' is parsed as a git option
        # (e.g. '--output=/path' writes an arbitrary file) instead of a revision.
        # -z: NUL-terminated and unquoted, so a name with a non-ASCII character or a line
        # separator other than \n (U+2028, NEL, form feed) is read as git wrote it (BACK-1731).
        diff_result = subprocess.run(
            ['git', 'diff', '--name-only', '-z', '--end-of-options', f'{since_ref}...HEAD'],
            capture_output=True, text=True, cwd=str(git_root), timeout=10, encoding='utf-8', errors='replace',
        )
        if diff_result.returncode != 0:
            err = diff_result.stderr.strip().splitlines()[0] if diff_result.stderr.strip() else f"unknown ref '{since_ref}'"  # boundary-ok: splitlines -- git subprocess output
            return set(), err
    except FileNotFoundError:
        return set(), "git not found"
    except subprocess.TimeoutExpired:
        return set(), "git diff timed out"

    changed: Set[str] = set()
    for rel in diff_result.stdout.split('\0'):
        if not rel:
            continue
        abs_path = git_root / rel
        changed.add(str(abs_path.resolve()))

    return changed, None


def _build_pack_import_graph(
    path: Path, failures: Optional[List[str]] = None,
) -> Tuple[Optional[Any], Set[Path]]:
    """Build reveal's multi-language import/dependency graph for *path*.

    Returns ``(graph, scanned_files)``, or ``(None, set())`` on any failure, and
    appends the failure's ``Type: message`` to *failures* when given, so the caller
    can say the signal it asked for is missing.
    Shared by ``_fetch_fan_in`` (--architecture) and ``_compute_graph_relevance``
    (--focus, BACK-833) so there is exactly one lazy-import/build site for
    ``ImportsAdapter`` in this module.
    """
    try:
        from reveal.adapters.imports import ImportsAdapter  # noqa: I006
        adapter = ImportsAdapter(resource=str(path), query='scope=path')  # BACK-1054: the path is the scan root
        adapter._build_graph(adapter._target_path)
        warnings = adapter.integrity_warnings(path)
        if warnings:
            if failures is not None:
                failures.extend(
                    f"Optional import graph for {to_posix(path)} is incomplete: {warning['message']}"
                    for warning in warnings)
            return None, set()
        return adapter.analysis.graph, adapter.analysis.scanned_files
    except Exception as e:  # boundary-ok: broad-except -- the import graph is an optional ranking signal built by the whole imports walk (tree-sitter parsing of every file, resolution; failure set not bounded) and a pack is still useful without it; the failure is returned in `failures` and shown as meta.relevance_warning
        logger.warning('pack: import graph for %s failed: %s', path, e)
        if failures is not None:
            failures.append(f'{type(e).__name__}: {e}')
        return None, set()


def _note_graph(graphs: Optional[List[Tuple[str, Any]]], kind: str, graph: Any) -> None:
    """Record the graph a ranking signal read, for ``_pack_edge_rule`` (a caller that does not
    state the rule passes no sink)."""
    if graphs is not None:
        graphs.append((kind, graph))


def _pack_edge_rule(graphs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """``{'edge_rule': ...}`` for the import edges the ranking read (BACK-2087), or nothing when it
    read none: every edge, function-level and test importers included, which is the view
    ``imports://?rank=fan-in`` counts by default."""
    if not graphs:
        return {}
    kinds = {kind for kind, _graph in graphs}
    subject = {
        (True, False): 'fan-in counts static imports between',
        (False, True): 'graph relevance follows static imports, in both directions, between',
        (True, True): 'fan-in counts, and graph relevance follows in both directions, static imports between',
    }[('fan_in' in kinds, 'relevance' in kinds)]
    return {'edge_rule': import_analysis.edge_rule(
        graphs[0][1], LAZY_INCLUDE, lazy_default=True, subject=subject, scope='scanned_path',
        hint=import_analysis.composed_rule_hint('pack'))}


def _fetch_fan_in(path: Path, failures: Optional[List[str]] = None, *,
                  graphs: Optional[List[Tuple[str, Any]]] = None) -> Dict[str, int]:
    """Return {abs_path: fan_in} for all files under *path* via ImportsAdapter.

    Returns empty dict on any failure — callers treat missing entries as fan_in=0
    (the failure is appended to *failures* when given). The graph the counts came from
    is appended to *graphs* when given (as ``('fan_in', graph)``), so the caller can state the rule they follow.
    """
    graph, scanned_files = _build_pack_import_graph(path, failures)
    if graph is None:
        return {}
    _note_graph(graphs, 'fan_in', graph)
    all_files = scanned_files | set(graph.files.keys()) | set(graph.reverse_deps.keys())
    return {str(f): len(graph.reverse_deps.get(f, set())) for f in all_files}


def _compute_graph_relevance(
    path: Path, focus: Optional[str], failures: Optional[List[str]] = None, *,
    graphs: Optional[List[Tuple[str, Any]]] = None,
) -> Dict[str, float]:
    """Personalized-PageRank relevance score per file, seeded from --focus (BACK-833).

    Builds reveal's own multi-language import/dependency graph (the same one
    ``--architecture``'s fan-in reads from, via ImportsAdapter) and runs a
    random-walk-with-restart from the files whose path matches *focus* (same
    substring match ``_compute_priority`` already uses). Relevance propagates
    along both edge directions — a file a focus file imports, or a file that
    imports a focus file, is relevant to it — so a file conceptually tied to
    the focus area but not literally named after it still gets ranked above
    an unrelated file. Closes the gap the plain focus-substring match leaves:
    that match only ever rewards a literal name hit.

    Returns {abs_path: score in [0, 1]}; empty on no focus, no matching seed
    files, or any graph-construction failure — callers treat missing entries
    as 0 (pure relevance signal, additive on top of the existing heuristic). The graph
    the scores walked is appended to *graphs* when given (see ``_fetch_fan_in``).
    """
    if not focus:
        return {}
    graph, scanned_files = _build_pack_import_graph(path, failures)
    if graph is None:
        return {}

    all_files = scanned_files | set(graph.files.keys()) | set(graph.reverse_deps.keys())
    if not all_files:
        return {}

    focus_lower = focus.lower()
    seeds = [f for f in all_files if focus_lower in str(f).lower()]
    if not seeds:
        return {}
    _note_graph(graphs, 'relevance', graph)

    # Undirected adjacency: an import edge signals relevance in either
    # direction, not just "depends on."
    adjacency = {
        f: set(graph.dependencies.get(f, set())) | set(graph.reverse_deps.get(f, set()))
        for f in all_files
    }

    seed_weight = 1.0 / len(seeds)
    personalization = {f: (seed_weight if f in seeds else 0.0) for f in all_files}
    scores = dict(personalization)

    damping = 0.85
    for _ in range(30):
        new_scores = {f: (1 - damping) * personalization[f] for f in all_files}
        for f in all_files:
            neighbors = adjacency[f]
            if not neighbors:
                continue
            share = damping * scores[f] / len(neighbors)
            for nb in neighbors:
                new_scores[nb] += share
        scores = new_scores

    max_score = max(scores.values()) if scores else 0.0
    if max_score <= 0:
        return {}
    return {str(f): v / max_score for f, v in scores.items()}


def _get_file_raw_content(file_path: str, max_lines: int = 500) -> str:
    """Return raw file content, truncated to max_lines if needed.

    Used for changed files in ``--content`` mode — raw content lets the agent
    see exactly what changed, not just the structural outline. Raises OSError
    when the file can't be read; _tiered_content records it.
    """
    text = Path(file_path).read_text(encoding='utf-8', errors='replace')
    lines = split_lines(text, keepends=True)
    if len(lines) > max_lines:
        truncated = ''.join(lines[:max_lines])
        remaining = len(lines) - max_lines
        return truncated + f'[... {remaining} more lines not shown — use reveal {file_path} to see full file]\n'
    return text


def _get_file_structure(file_path: str) -> str:
    """Return reveal structure output for a file as a string.

    Uses reveal's own progressive-disclosure analysis — same output as `reveal file.py`.
    Returns an empty string if no analyzer handles the file; an analysis failure
    raises, and _tiered_content records it.
    """
    from types import SimpleNamespace  # noqa: I006 — avoid circular import at module level
    from reveal.registry import get_analyzer  # noqa: I006
    from reveal.display.structure import show_structure  # noqa: I006

    analyzer_class = get_analyzer(file_path, allow_fallback=True)
    if not analyzer_class:
        return ''
    analyzer = analyzer_class(file_path)

    buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buffer
    try:
        # BACK-1183: pack --content must stay strictly structural even for a
        # file too small to have extractable structure -- the shared
        # show_structure() pipeline's <=50-line raw-source fallback (a
        # helpful default for interactive `reveal file.py`) would otherwise
        # leak a small file's full content into a confidentiality-sensitive
        # DD pack.
        # all=True: pack budgets its own output; the interactive per-file item cap must not apply.
        show_structure(analyzer, 'text', args=SimpleNamespace(no_raw_fallback=True, all=True))
    finally:
        sys.stdout = old_stdout

    return buffer.getvalue()


_STRUCTURE_THRESHOLD = 2.0


def _tiered_content(file_info: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    """(content_type, content, error) for one selected file, by tier.

    ``error`` names why the content is missing, so an unreadable file or a crashed
    analysis is never shown as an empty one (BACK-1614). Analysis catches anything:
    one file's analyzer bug must not abort the whole pack.
    """
    path = file_info['path']
    if file_info.get('changed', False):
        try:
            return 'full', _get_file_raw_content(path), None
        except OSError as e:
            return 'full', '', f'unreadable: {failure_of(e).cause}'
    if file_info.get('priority', _STRUCTURE_THRESHOLD) >= _STRUCTURE_THRESHOLD:
        try:
            return 'structure', _get_file_structure(path), None
        except Exception as e:  # boundary-ok: broad-except -- the analyzer runs on an arbitrary user file in any of reveal's languages (tree-sitter, custom parsers; failure set not bounded) and one file must not abort the pack; the entry carries `error` and a warning is logged
            logger.warning('Structure analysis failed for %s: %s', path, e)
            return 'structure', '', f'structure analysis failed: {type(e).__name__}: {e}'
    return 'name_only', '', None


def _collect_file_contents(selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return tiered content for each selected file as a list of dicts (JSON mode).

    Each entry includes ``content_type``: ``'full'`` (changed files), ``'structure'``
    (key files), or ``'name_only'`` (low-priority files), and ``error`` when the
    file could not be read or analyzed.
    """
    result = []
    for file_info in selected:
        content_type, content, error = _tiered_content(file_info)
        entry = {
            'file': file_info['relative'],
            'changed': file_info.get('changed', False),
            'content_type': content_type,
            'content': content,
        }
        if error:
            entry['error'] = error
        result.append(entry)
    return result


def _parse_budget(budget_str: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse budget string into (tokens, lines)."""
    if budget_str.endswith('-lines'):
        try:
            return None, int(budget_str[:-6])
        except ValueError:
            pass
    try:
        return int(budget_str), None
    except ValueError:
        return 2000, None


def _record_candidate_discovery_warning(
    path: Path, failures: Sequence[OSError], meta: Dict[str, Any],
) -> None:
    """Disclose actual candidate loss without changing Pack's legacy outcome policy."""
    warning = traversal_failed_warning([
        failure_of(error)
        for error in failures], path)
    if warning:
        warning['message'] = (
            'Pack candidate discovery is incomplete; candidate population is unknown; '
            'counts and rankings cover observed eligible files only; ' + warning['message'])
        meta.setdefault('warnings', []).append(warning)


_FileMeasurementFailure = Tuple[str, str, str]


def _file_measurement_failure(path: Path, operation: str, error: OSError) -> _FileMeasurementFailure:
    return to_posix(path), operation, failure_of(error).cause


def _candidate_measurements(files, on_file_error):
    """Reuse one adopted stat for eligibility, ranking and measured row facts."""
    for path in files:
        if on_file_error is None:
            if path.name == '__init__.py' and path.stat().st_size < 500:
                continue
            yield path, None
            continue
        try:
            measured = path.stat()
        except OSError as error:
            on_file_error(_file_measurement_failure(path, 'stat', error))
            continue
        if path.name != '__init__.py' or measured.st_size >= 500:
            yield path, measured


def _candidate_lines(path: Path, on_file_error) -> Optional[int]:
    if on_file_error is None:
        return _count_lines(path)
    errors: List[OSError] = []
    lines = _count_lines(path, on_error=errors.append)
    if errors:
        on_file_error(_file_measurement_failure(path, 'line_count', errors[0]))
        return None
    return lines


def _candidate_stat(path: Path, measured):
    return path.stat() if measured is None else measured


def _priority_size(measured) -> dict:
    return {} if measured is None else {'size_bytes': measured.st_size}


def _record_file_measurement_warning(failures: Sequence[_FileMeasurementFailure], meta: Dict[str, Any]) -> None:
    """FILE costs and eligibility are distinct from directory population loss."""
    if not failures:
        return
    shown = list(dict.fromkeys(failures))[:5]
    detail = '; '.join(f'{path} ({operation}: {cause})' for path, operation, cause in shown)
    suffix = '; additional file measurement failures omitted' if len(set(failures)) > len(shown) else ''
    meta.setdefault('warnings', []).append({
        'type': 'file_measurement_failed',
        'files': [path for path, _, _ in shown],
        'operations': sorted({operation for _, operation, _ in failures}),
        'causes': [f'{operation}: {cause}' for _, operation, cause in shown],
        'message': ('Pack candidate file measurements are incomplete; counts and rankings cover '
                    'observed measured candidates only; unknown line costs are unavailable '
                    f'and excluded from line budgets: {detail}{suffix}'),
    })


def _collect_candidates(
    path: Path,
    focus: Optional[str],
    changed_files: Optional[Set[str]] = None,
    fan_in_scores: Optional[Dict[str, int]] = None,
    graph_relevance_scores: Optional[Dict[str, float]] = None,
    exclude_patterns: Optional[List[str]] = None,
    *,
    on_error: Optional[Callable[[OSError], None]] = None,
    on_file_error: Optional[Callable[[_FileMeasurementFailure], None]] = None,
) -> List[Dict[str, Any]]:
    """Collect and score candidate files for the pack."""
    candidates: List[Dict[str, Any]] = []

    measurements = list(_candidate_measurements(
        _walk_files(path, exclude_patterns=exclude_patterns, on_error=on_error), on_file_error))
    files = [file for file, _ in measurements]

    # BACK-1206: a monorepo can have one _ENTRY_POINT_CONFIG_FILES-name
    # (package.json, Cargo.toml, ...) per sub-package/plugin — dozens of
    # legitimate-but-shallow manifests would otherwise all claim the same
    # unconditional +10.0 "one per project" bonus BACK-1196 reserved for a
    # real project root, flooding the budget the same way repeated
    # index.js/main.py barrels did before that fix. Only the shallowest
    # occurrence(s) of each config filename — the project's own root config,
    # not a nested package's — keep the full bonus.
    min_depth_by_name: Dict[str, int] = {}
    for f in files:
        if _is_entry_config_file(f.name):
            depth = len(f.relative_to(path).parts)
            if depth < min_depth_by_name.get(f.name, depth + 1):
                min_depth_by_name[f.name] = depth

    for f, measured in measurements:
        rel = f.relative_to(path)
        stat = _candidate_stat(f, measured)
        size_chars = stat.st_size
        tokens_approx = size_chars // _APPROX_CHARS_PER_TOKEN
        lines = _candidate_lines(f, on_file_error)

        is_changed = bool(changed_files and str(f.resolve()) in changed_files)
        fan_in = (fan_in_scores or {}).get(str(f.resolve()), 0)
        graph_relevance = (graph_relevance_scores or {}).get(str(f.resolve()), 0.0)
        is_root_config = len(rel.parts) == min_depth_by_name.get(f.name, -1)
        priority = _compute_priority(
            f, rel, focus, is_changed=is_changed, fan_in=fan_in,
            graph_relevance=graph_relevance, is_root_config=is_root_config, **_priority_size(measured),
        )
        # BACK-1195/B2-4: same classifier _compute_priority now scores on
        # (BACK-1266 follow-up, 2026-09-02) -- this was the "future ranking
        # change" the original comment here named but never wired in, which
        # is exactly why a Rails spec/dummy/ harness file (test-provenance
        # by directory, not by the old hardcoded {'test','tests',...}
        # literal-name set _compute_priority used to check) could out-rank
        # real application code in a budget-constrained pack.
        provenance = classify_path_provenance(rel.parts[:-1], rel.name)

        candidates.append({
            'path': to_posix(f),  # '/' on every OS (BACK-1586)
            'relative': to_posix(rel),
            'priority': priority,
            'tokens_approx': tokens_approx,
            'lines': lines,
            'mtime': stat.st_mtime,
            'size': stat.st_size,
            'changed': is_changed,
            'fan_in': fan_in,
            'graph_relevance': graph_relevance,
            # BACK-1195: mark each candidate's provenance so a reader can
            # discount vendored/generated/test noise in place.
            'provenance': provenance,
        })

    # Sort: priority descending, then mtime descending
    candidates.sort(key=lambda c: (-c['priority'], -c['mtime']))
    return candidates


def _file_size(path: Path, size_bytes: Optional[int]) -> int:
    return path.stat().st_size if size_bytes is None else size_bytes


def _compute_priority(
    path: Path,
    rel: Path,
    focus: Optional[str],
    is_changed: bool = False,
    fan_in: int = 0,
    graph_relevance: float = 0.0,
    is_root_config: bool = True,
    *,
    size_bytes: Optional[int] = None,
) -> float:
    """Score a file's priority for inclusion in the pack."""
    name = path.name.lower()
    rel_str = str(rel).lower()
    # Path segments without extension, for whole-component matching
    rel_parts = {p.lower() for p in rel.parts}
    rel_stem = path.stem.lower()
    score = 0.0

    # Changed files (--since): highest priority — above entry points
    if is_changed:
        score += 20.0

    # Entry points: highest priority. BACK-1196: gate the bonus on content
    # for the convention-based names (_ENTRY_POINT_PATTERNS) the same way
    # __init__.py already is below — 'index.js'/'main.py'/etc. are
    # resolution/routing CONVENTIONS, not guaranteed real entry points. A
    # flat basename match previously scored these 10.0 (5x a real logic
    # module's 2.0) with no size/content check at all, so a tree of
    # near-empty barrel files could dominate a budget-constrained selection.
    # Config/build files (Makefile, package.json, ...) are one-per-project,
    # not a repeated convention, so they keep the full bonus unconditionally
    # for the project's own root config. BACK-1206: a monorepo can have one
    # of these per sub-package/plugin too — a non-root instance (caller has
    # already determined a shallower same-named file exists) falls through
    # to ordinary scoring instead of claiming the same ONE-per-project bonus.
    if _is_entry_config_file(name) and is_root_config:
        score += 10.0
    elif _is_entry_point_name(name):
        file_size = _file_size(path, size_bytes)
        if file_size > 2000:
            score += 10.0
        elif file_size >= 500:
            # Below a real logic module's 2.0 — same tier discipline as the
            # __init__.py bonus below, so a thin-but-real entry point still
            # lands in "Other files", not "Key modules".
            score += 1.0
        # < 500 bytes: no bonus — indistinguishable from a near-empty
        # re-export/routing stub without deeper content analysis.

    # __init__.py: modest bonus only for substantial ones (re-export stubs
    # < 500 bytes are already excluded by _collect_candidates). Score below
    # regular modules (0.5 vs 2.0) so they land in "Other files" tier and
    # don't displace real logic files from "Key modules" tier.
    if name == '__init__.py' and _file_size(path, size_bytes) > 2000:
        score += 0.5

    # Focus pattern match: high bonus
    if focus and focus.lower() in rel_str:
        score += 8.0

    # Graph relevance (BACK-833): personalized-PageRank score seeded from
    # --focus, propagated along the import/dependency graph. Additive on top
    # of the literal substring match above — it rewards files structurally
    # tied to the focus area even when their name doesn't mention it.
    if graph_relevance > 0:
        score += graph_relevance * 6.0

    # Key directories — match whole path components only to avoid substring false
    # positives (e.g. 'main' inside 'maintainability', 'core' inside 'decorator')
    if rel_parts & _KEY_DIR_SEGMENTS or rel_stem in _KEY_DIR_SEGMENTS:
        score += 2.0

    # Fan-in boost (--architecture): widely-imported files are core abstractions
    if fan_in >= 15:
        score += 5.0
    elif fan_in >= 5:
        score += 3.0
    elif fan_in >= 1:
        score += 1.0

    # Penalize test/vendor files via the shared classify_path_provenance
    # verdict (BACK-1266 follow-up, 2026-09-02) rather than a private
    # literal-name set. That old set only matched a directory named exactly
    # 'test'/'tests'/'vendor' -- it missed 'spec'/'specs' entirely (Rails'
    # spec/dummy/ harness convention: dummy is not itself the test-dir
    # marker, 'spec' is, and 'spec' wasn't in the set) and every
    # PascalCase/multi-language test convention BACK-1252 already taught the
    # shared classifier. Filename-based test detection (test_/_test prefix,
    # PascalCase *Test suffix) is also folded in here now, replacing the
    # separate substring scan below for that part.
    if classify_path_provenance(rel.parts[:-1], rel.name) in ('test', 'vendor'):
        score -= 3.0
    # Remaining noise categories classify_path_provenance doesn't cover
    # (it classifies test/vendor/minified/first-party, not "supporting
    # docs" or build caches).
    if rel_parts & {'docs', '__pycache__'}:
        score -= 3.0
    if '/.' in rel_str:
        score -= 3.0

    # BACK-526: non-source data/markup files (localization tables, data blobs,
    # standalone docs) are supporting material, not "key modules" of the code.
    # Without this, a file like Localization/Core/si.json scored +2.0 purely
    # from the 'core' key-dir segment and surfaced in the "Key modules" tier
    # ahead of real source. Demote them below the Key-modules threshold unless
    # they carry a genuine structural signal — a recognized entry-point config
    # (package.json, pyproject.toml, …) or a non-zero fan-in (--architecture),
    # both of which mark a data file that really is central.
    if (
        path.suffix.lower() in _DATA_MARKUP_EXTENSIONS
        and fan_in == 0
        and not _is_entry_point_name(name)
        and not (_is_entry_config_file(name) and is_root_config)
    ):
        score -= 2.0

    # Penalize very large files (noisy)
    if _file_size(path, size_bytes) > 50_000:
        score -= 1.0

    return max(score, 0.0)


def _apply_budget(
    candidates: List[Dict[str, Any]],
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
    base_path: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Select files within the budget."""
    selected = []
    used_tokens = 0
    used_lines = 0
    lines_unavailable = False
    skipped = 0
    line_budget_incomplete = False

    for c in candidates:
        if budget_lines is not None and c['lines'] is None:
            skipped += 1
            line_budget_incomplete = True
            continue
        if budget_tokens is not None:
            if used_tokens + c['tokens_approx'] > budget_tokens:
                skipped += 1
                continue
            used_tokens += c['tokens_approx']

        if budget_lines is not None:
            if used_lines + c['lines'] > budget_lines:
                skipped += 1
                continue

        if c['lines'] is None:
            lines_unavailable = True
        else:
            used_lines += c['lines']
        selected.append(c)

    meta = {
        'total_candidates': len(candidates),
        'selected': len(selected),
        'skipped': skipped,
        'used_tokens_approx': used_tokens,
        'used_lines': None if lines_unavailable else used_lines,
        'budget_tokens': budget_tokens,
        'budget_lines': budget_lines,
    }
    if line_budget_incomplete:
        meta['line_budget_incomplete'] = True
    return selected, meta


def _walk_files(
    path: Path, exclude_patterns: Optional[List[str]] = None,
    *, on_error: Optional[Callable[[OSError], None]] = None,
) -> Generator[Path, None, None]:
    """Yield code/config files under *path* (respects common ignores).

    BACK-1196: *exclude_patterns* (from ?exclude=, the inverse of ?focus=)
    lets a caller drop a whole area (fixtures, generated code, a vendored
    subtree) from candidacy entirely, rather than only being able to boost
    relevance elsewhere. Gitignore syntax, the same matcher every walk uses
    (BACK-1576).
    """
    # BACK-1032: union the registry's full code-extension set (58+, all
    # tree-sitter-backed languages) with the doc/config extras pack wants
    # beyond "code" — a hand-maintained list silently dropped whole
    # languages (Dart, Lua, Zig, Haskell, ...) from the LLM-context snapshot.
    _CODE_EXTENSIONS = get_code_extensions() | {
        '.sh', '.bash', '.yaml', '.yml', '.toml', '.json', '.md',
        '.sql', '.html', '.css', '.scss',
    }
    _ROOT_FILES = {'Makefile', 'Dockerfile', 'pyproject.toml', 'package.json',
                   'Cargo.toml', 'go.mod', 'requirements.txt', 'setup.py'}

    if path.is_file():
        yield path
        return

    # The display walk (BACK-1581): pack:// packs what `reveal DIR` shows -- noise and
    # dot dirs never entered, gitignore, REVEAL_IGNORE and --exclude/?exclude= applied.
    for item in _walk_code_files(path, exclude_patterns, purpose=DISPLAY, on_error=on_error):
        # Include root config files
        if item.parent == path and item.name in _ROOT_FILES:
            yield item
            continue
        # Include code files by extension
        if item.suffix.lower() in _CODE_EXTENSIONS:
            yield item


def _count_lines(path: Path, *, on_error: Optional[Callable[[OSError], None]] = None) -> int:
    """Count lines in a file."""
    try:
        return path.read_text(encoding='utf-8', errors='ignore').count('\n')
    except OSError as error:
        # Default callers retain the historical integer fallback. Adopted callers
        # receive the cause and distinguish unknown cost from a measured zero.
        if on_error is not None:
            on_error(error)
        return 0


def _budget_text(value: Any) -> str:
    """Keep the raw budget spelling; a bare 0/1 may arrive as a bool (BACK-1180)."""
    return str(int(value)) if isinstance(value, bool) else str(value)


def _optional_text(value: Any) -> Optional[str]:
    return str(value) or None


def _legacy_flag(value: Any) -> bool:
    """Pack's historical boolean reading: true/yes/1 enable, anything else is false."""
    return value is True or str(value).lower() in ('true', 'yes', '1')


_BUDGET = ParamSpec('budget', 'string', 'Token or line budget (e.g. 2000, 500-lines)', '2000',
                    _budget_text, ('budget=4000', 'budget=500-lines'), role='analysis',
                    cli=CliBinding(('--budget',), metavar='N[=tokens|-lines]'))
_FOCUS = ParamSpec('focus', 'string', 'Emphasize files matching this name pattern', None,
                   _optional_text, ('focus=auth',), role='analysis', uri_codec='percent',
                   cli=CliBinding(('--focus',), metavar='TOPIC'))
_SINCE = ParamSpec('since', 'string', 'Git ref to diff against; changed files boosted to top priority',
                   None, _optional_text, ('since=main',), role='analysis', uri_codec='percent',
                   cli=CliBinding(('--since',), metavar='REF'))
_CONTENT = ParamSpec('content', 'boolean', 'Include tiered file content (full/structure/name_only)',
                     False, _legacy_flag, ('content=true',), role='presentation',
                     cli=CliBinding(('--content',), action='store_true'))
_ARCHITECTURE = ParamSpec('architecture', 'boolean', 'Boost high fan-in files; include an architecture hint',
                          False, _legacy_flag, ('architecture=true',), role='analysis',
                          cli=CliBinding(('--architecture',), action='store_true'))


_REQUIRED_WARNINGS = {'analysis_incomplete', 'file_measurement_failed'}

_HELP_EPILOG = (
    "Examples:\n"
    "  reveal pack ./src                      # Default 2000-token budget\n"
    "  reveal pack ./src --budget 4000        # 4000-token budget\n"
    "  reveal pack ./src --budget 500-lines   # 500-line budget\n"
    "  reveal pack ./src --focus auth         # Emphasize auth module\n"
    "  reveal pack ./src --since main         # PR review: changed files first\n"
    "  reveal pack ./src --since HEAD~3       # Changes since 3 commits ago\n"
    "  reveal pack ./src --content            # Emit structure content (agent-ready)\n"
    "  reveal pack ./src --content --since main --budget 8000  # Full agent context\n"
    "  reveal pack ./src --format json        # Structured output for tooling\n"
    "  reveal pack ./src --architecture       # Boost core abstractions; show architecture brief\n"
    "\n"
    "Prioritization order:\n"
    "  1. Changed files (with --since; git diff vs ref)\n"
    "  2. Entry points and root config (main.py, index.js, package.json, etc.)\n"
    "  3. Files matching --focus, and files tied to them by imports\n"
    "  4. Key directories (api/, core/, models/, auth/, ...) and, with\n"
    "     --architecture, widely imported files\n"
    "  5. Other files (fills remaining budget); tests, vendor and docs last\n"
    "  Ties go to the most recently modified file.\n"
    "\n"
    "--architecture and --focus rank by import edges and print the rule they\n"
    "counted by (a Rule: line; edge_rule in JSON): function-level imports and\n"
    "test importers count.\n"
    "--budget counts the raw size of the files selected, not the output.\n"
    "With --content: changed files are shown raw (first 500 lines), key files\n"
    "as structure, and the remaining selected files by name only.\n"
)


def _is_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _pack_proof_error(result: Any) -> Optional[str]:
    """Validate the uncapped candidate counts; presentation cuts may hide rows but not these."""
    if not isinstance(result, dict) or not isinstance(result.get('meta'), dict):
        return 'Required pack answer is malformed'
    if 'files' in result and not isinstance(result['files'], list):
        return 'Required pack file selection is malformed'
    meta = result['meta']
    total, selected, skipped = (meta.get(key) for key in ('total_candidates', 'selected', 'skipped'))
    if not all(_is_count(count) for count in (total, selected, skipped)):
        return 'Required candidate counts are missing or malformed'
    if selected + skipped != total:
        return 'Required candidate counts disagree with each other'
    return None


@register_adapter('pack')
@register_renderer(PackRenderer)
class PackAdapter(ResourceAdapter):
    """Adapter curating a token-budgeted context snapshot for LLM consumption:
    ranks candidate files by priority (entry points, fan-in, focus/graph
    relevance, changed-since-ref) and selects as many as fit the budget."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    # Carry URI verbose through the result; the renderer also accepts CLI options.
    CLI_QUERY_FLAGS = {'verbose': 'verbose', 'respect_gitignore': 'respect_gitignore=false'}

    RESULT_TYPE = 'pack'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(cli_default=None, required=True, uri_codec='existing-path-first')
    PARAM_SPECS = (_BUDGET, _FOCUS, _SINCE, _CONTENT, _ARCHITECTURE)

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)  # BACK-507
        # Populated by get_structure(); CLI needs this for its stderr warning,
        # but it's not part of the JSON contract (only meta.since is).
        self.since_error: Optional[str] = None
        # Same pattern, for BACK-1006: fan_in/graph_relevance are opt-in
        # (--architecture / --focus) for performance on large repos, but
        # nothing said so when neither is passed -- files were silently
        # ranked by filename/entry-point heuristics alone while `pack --help`
        # and the adapter's own priority-ranking description read as though
        # fan-in/relevance are always part of the ranking.
        self.relevance_warning: Optional[str] = None

    @staticmethod
    def answer_requirement_error(result, expected_type, prior_facts=None):
        return _pack_proof_error(result)

    @staticmethod
    def execution_facts(result):
        """D6: lost candidate discovery or measurement is incomplete work, never a clean answer."""
        if _pack_proof_error(result):
            return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
        meta = result['meta']
        lost = any(w.get('type') in _REQUIRED_WARNINGS for w in meta.get('warnings', []))
        if lost:
            usable = meta['total_candidates'] > 0
            return result_execution_facts(
                result, completeness=AnalysisCompleteness.INCOMPLETE if usable
                else AnalysisCompleteness.FAILED)
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'pack',
            'description': 'Curate a token-budgeted context snapshot for LLM consumption.',
            'syntax': 'pack://<path>[?budget=2000&focus=auth&since=main&content=true&architecture=true]',
            'examples': [
                {'uri': 'pack://src', 'description': 'Default 2000-token budget'},
                {'uri': 'pack://src?budget=4000', 'description': '4000-token budget'},
                {'uri': 'pack://src?since=main', 'description': 'PR review: changed files first'},
                {'uri': 'pack://src?content=true', 'description': 'Emit structure content (agent-ready)'},
            ],
            'features': [
                'Priority ranking: changed files (--since) > entry points > focus/graph relevance > fan-in > recency',
                'Token or line budget enforcement',
                'Tiered content emission: changed=full content, key files=structure, low-priority=names only',
                "Each candidate is tagged files[].provenance: 'test'/'vendor'/'minified'/null "
                '(first-party) — BACK-1195, cheap path-only classification, no ranking-order '
                'change (yet).',
            ],
            'notes': [
                'Token counts are approximate (chars / 4), not a real tokenizer.',
                'architecture=true and focus= rank by import edges and state the rule they counted by '
                '(a Rule: line in text, edge_rule in JSON); function-level imports and test importers count.',
            ],
            'see_also': [
                'reveal pack <path> - CLI subcommand form',
                'reveal_pack MCP tool - same ranking, MCP-native',
            ],
            'output_formats': ['text', 'json'],
            'epilog': _HELP_EPILOG,
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'pack',
            'description': 'Token-budgeted context snapshot: ranked file selection for LLM consumption',
            'uri_syntax': 'pack://<path>?budget=2000&focus=auth&since=main&content=true&architecture=true',
            'resource': PackAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': 'none', 'fail_on': ['none']},
            'query_params': {
                **param_schema(PackAdapter.PARAM_SPECS),
                'exclude': {'type': 'string', 'description': 'Comma-separated patterns to drop from candidacy entirely (inverse of focus=)', 'examples': ['exclude=spec/*,vendor/*']},
                'verbose': {'type': 'flag', 'description': 'Show per-file token/line-count breakdown. Same as the CLI --verbose', 'examples': ['pack://src?verbose']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'pack',
                    'description': 'Ranked, budget-selected files plus selection metadata',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'meta': {'type': 'object'},
                            'files': {'type': 'array'},
                            'edge_rule': {'type': 'object'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'pack://src', 'description': 'Default 2000-token pack for src/', 'output_type': 'pack'},
            ],
            'notes': [
                '--architecture and --focus both build reveal\'s own import/dependency graph via imports:// machinery.',
            ],
        }

    def get_structure(self, verbose: bool = False, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        # BACK-1180: a bare budget=0 stays '0'; declared binding keeps the raw spelling.
        budget_str = _BUDGET.read(self.query_params)
        focus = _FOCUS.read(self.query_params)
        since = _SINCE.read(self.query_params)
        emit_content = _CONTENT.read(self.query_params)
        architecture = _ARCHITECTURE.read(self.query_params)
        # BACK-1196: ?exclude= is the inverse of ?focus= — drop a whole area
        # (fixtures, generated code, a vendored subtree) from candidacy
        # entirely, comma-separated, same format as overview://'s ?exclude=.
        exclude_param = self.query_params.get('exclude')
        exclude_patterns = (
            split_exclude_param(exclude_param) or None
        )

        budget_tokens, budget_lines = _parse_budget(budget_str)

        changed_files: Set[str] = set()
        if since:
            changed_files, self.since_error = _get_changed_files(path, since)

        graph_failures: List[str] = []
        graphs: List[Tuple[str, Any]] = []
        fan_in_scores = _fetch_fan_in(path, graph_failures, graphs=graphs) if architecture else None
        graph_relevance_scores = (_compute_graph_relevance(path, focus, graph_failures, graphs=graphs)
                                  if focus else {})

        if graph_failures:
            # The signal was asked for and could not be built: without this, every file
            # reads as fan-in 0 / relevance 0 and the ranking looks computed.
            asked = ' and '.join(n for n, on in (('fan-in', architecture), ('graph-relevance', bool(focus))) if on)
            self.relevance_warning = (
                f"{asked} not computed completely; the optional import graph is unavailable or incomplete "
                f"({'; '.join(dict.fromkeys(graph_failures))}) "
                "-- files are ranked by filename/entry-point heuristics and recency only"
            )
        elif not architecture and not focus:
            self.relevance_warning = (
                "fan-in and graph-relevance signals were not computed (pass "
                "--architecture and/or --focus to enable) -- files are "
                "ranked by filename/entry-point heuristics and recency only"
            )

        discovery_failures: List[OSError] = []
        file_failures: List[_FileMeasurementFailure] = []
        candidates = _collect_candidates(
            path, focus, changed_files, fan_in_scores=fan_in_scores,
            graph_relevance_scores=graph_relevance_scores,
            exclude_patterns=exclude_patterns, on_error=discovery_failures.append,
            on_file_error=file_failures.append,
        )
        selected, meta = _apply_budget(candidates, budget_tokens, budget_lines, path)
        _record_candidate_discovery_warning(path, discovery_failures, meta)
        _record_file_measurement_warning(tuple(file_failures), meta)
        if since:
            meta['since'] = since
            meta['changed_files_count'] = len(changed_files)
        if self.since_error:
            # Optional signal: candidates stay ranked without it, the cause stays visible.
            meta['since_error'] = self.since_error
        if self.relevance_warning:
            meta['relevance_warning'] = self.relevance_warning

        report: Dict[str, Any] = {
            'path': to_posix(path),
            'budget': budget_str,
            'since': since,
            'files': selected,
        }
        if architecture:
            report['architecture'] = True
        report.update(_pack_edge_rule(graphs))
        if emit_content:
            report['content'] = _collect_file_contents(selected)
        # BACK-1379: carry ?verbose through the result dict since handle_uri
        # doesn't forward a verbose= render kwarg for this renderer.
        if verbose or 'verbose' in self.query_params:
            report['verbose'] = True

        return ResultBuilder.create(
            result_type='pack',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            meta=meta,
            data=report,
        )
