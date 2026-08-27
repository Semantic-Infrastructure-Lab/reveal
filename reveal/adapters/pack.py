"""pack:// adapter - token-budgeted context snapshot for LLM consumption.

Scan/rank/render logic lives here (BACK-901/BACK-961); `cli/commands/pack.py`
is a thin argparse shim over this adapter. The reveal_pack MCP tool imports
five of these internal functions directly (_parse_budget, _get_changed_files,
_collect_candidates, _apply_budget, _format_pack_result) rather than going
through run_pack — all five keep their exact names/signatures, re-exported
from cli/commands/pack.py, so the MCP tool is untouched by this refactor.
"""

import io
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

from reveal.reveal_types import CONTRACT_VERSION
from reveal.registry import get_code_extensions

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import print_json_result
from ..utils.path_utils import is_skippable_dir, to_posix
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder

# Entry point filename patterns (highest priority)
_ENTRY_POINT_PATTERNS = {
    'main.py', 'app.py', 'server.py', 'index.py', 'cli.py', 'run.py',
    'wsgi.py', 'asgi.py',
    'main.js', 'index.js', 'app.js', 'server.js',
    'main.ts', 'index.ts', 'app.ts',
    'main.go', 'main.rb', 'main.rs',
}
# __init__.py excluded from unconditional entry points — most are near-empty;
# only promote them if they have substantial content (scored by size below)

# BACK-1196: config/build files are ONE PER PROJECT, not a resolution/routing
# convention repeated across a tree the way 'index.js'/'main.py' are (a
# monorepo can have hundreds of near-empty index.js barrel files — Discourse
# scored 27 of them into an 8K-budget pack, ZERO substantive application
# code). These always keep the full entry-point bonus regardless of size —
# a small package.json/Cargo.toml is still a unique, legitimate signal.
_ENTRY_POINT_CONFIG_FILES = {
    'Makefile', 'Dockerfile', 'pyproject.toml', 'package.json', 'Cargo.toml',
}

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
            capture_output=True, text=True, cwd=str(path), timeout=10,
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
        diff_result = subprocess.run(
            ['git', 'diff', '--name-only', '--end-of-options', f'{since_ref}...HEAD'],
            capture_output=True, text=True, cwd=str(git_root), timeout=10,
        )
        if diff_result.returncode != 0:
            err = diff_result.stderr.strip().splitlines()[0] if diff_result.stderr.strip() else f"unknown ref '{since_ref}'"
            return set(), err
    except FileNotFoundError:
        return set(), "git not found"
    except subprocess.TimeoutExpired:
        return set(), "git diff timed out"

    changed: Set[str] = set()
    for rel in diff_result.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        abs_path = git_root / rel
        changed.add(str(abs_path.resolve()))

    return changed, None


def _build_pack_import_graph(path: Path) -> Tuple[Optional[Any], Set[Path]]:
    """Build reveal's multi-language import/dependency graph for *path*.

    Returns ``(graph, scanned_files)``, or ``(None, set())`` on any failure.
    Shared by ``_fetch_fan_in`` (--architecture) and ``_compute_graph_relevance``
    (--focus, BACK-833) so there is exactly one lazy-import/build site for
    ``ImportsAdapter`` in this module.
    """
    try:
        from reveal.adapters.imports import ImportsAdapter  # noqa: I006
        adapter = ImportsAdapter(resource=str(path))
        adapter._build_graph(adapter._target_path)
        return adapter._graph, adapter._scanned_files
    except Exception:
        # Documented fallback: fan-in/relevance are additive scoring signals,
        # not required for a pack to succeed — callers treat a missing graph as 0.
        return None, set()


def _fetch_fan_in(path: Path) -> Dict[str, int]:
    """Return {abs_path: fan_in} for all files under *path* via ImportsAdapter.

    Returns empty dict on any failure — callers treat missing entries as fan_in=0.
    """
    graph, scanned_files = _build_pack_import_graph(path)
    if graph is None:
        return {}
    all_files = scanned_files | set(graph.files.keys()) | set(graph.reverse_deps.keys())
    return {str(f): len(graph.reverse_deps.get(f, set())) for f in all_files}


def _compute_graph_relevance(path: Path, focus: Optional[str]) -> Dict[str, float]:
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
    as 0 (pure relevance signal, additive on top of the existing heuristic).
    """
    if not focus:
        return {}
    graph, scanned_files = _build_pack_import_graph(path)
    if graph is None:
        return {}

    all_files = scanned_files | set(graph.files.keys()) | set(graph.reverse_deps.keys())
    if not all_files:
        return {}

    focus_lower = focus.lower()
    seeds = [f for f in all_files if focus_lower in str(f).lower()]
    if not seeds:
        return {}

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
    see exactly what changed, not just the structural outline.
    """
    try:
        text = Path(file_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        # The text-mode caller renders '' as '[unreadable]' — visible to the
        # reader, just not at this call site.
        return ''
    lines = text.splitlines(keepends=True)
    if len(lines) > max_lines:
        truncated = ''.join(lines[:max_lines])
        remaining = len(lines) - max_lines
        return truncated + f'[... {remaining} more lines not shown — use reveal {file_path} to see full file]\n'
    return text


def _get_file_structure(file_path: str) -> str:
    """Return reveal structure output for a file as a string.

    Uses reveal's own progressive-disclosure analysis — same output as `reveal file.py`.
    Returns empty string if no analyzer is available or analysis fails.
    """
    from types import SimpleNamespace  # noqa: I006 — avoid circular import at module level
    from reveal.registry import get_analyzer  # noqa: I006
    from reveal.display.structure import show_structure  # noqa: I006

    try:
        analyzer_class = get_analyzer(file_path, allow_fallback=True)
        if not analyzer_class:
            return ''
        analyzer = analyzer_class(file_path)
    except Exception:
        return ''

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
        show_structure(analyzer, 'text', args=SimpleNamespace(no_raw_fallback=True))
    except Exception:
        # The text-mode caller renders '' as '[no structure analysis available]'.
        return ''
    finally:
        sys.stdout = old_stdout

    return buffer.getvalue()


def _emit_content_section(selected: List[Dict[str, Any]]) -> None:
    """Emit tiered content for each selected file.

    Three tiers based on priority and change status:
    - **Changed files** → full raw content (see exactly what changed)
    - **Non-changed, priority >= 2** → reveal structure (function signatures, imports)
    - **Non-changed, priority < 2** → name-only listing (preserve token budget)
    """
    _STRUCTURE_THRESHOLD = 2.0

    print()
    print('━' * 70)
    print('CONTENT  (changed=full · key files=structure · low priority=names)')
    print('━' * 70)

    name_only: List[Dict[str, Any]] = []

    for file_info in selected:
        rel = file_info['relative']
        file_path = file_info['path']
        is_changed = file_info.get('changed', False)
        priority = file_info.get('priority', _STRUCTURE_THRESHOLD)

        if is_changed:
            # Tier 0: full raw content — agent needs to see what actually changed
            content = _get_file_raw_content(file_path)
            print(f'\n── {rel}  ◀ CHANGED (full content) ──')
            if content.strip():
                print(content, end='' if content.endswith('\n') else '\n')
            else:
                print('[unreadable]')
        elif priority >= _STRUCTURE_THRESHOLD:
            # Tier 1/2: reveal structure — function signatures, class defs, imports
            content = _get_file_structure(file_path)
            print(f'\n── {rel} ──')
            if content.strip():
                print(content, end='' if content.endswith('\n') else '\n')
            else:
                print('[no structure analysis available]')
        else:
            # Tier 3: name only — deferred to summary to save tokens
            name_only.append(file_info)

    if name_only:
        print('\n── Low-priority files (selected, structure omitted) ──')
        for file_info in name_only:
            print(f'  {file_info["relative"]}')


def _collect_file_contents(selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return tiered content for each selected file as a list of dicts (JSON mode).

    Each entry includes ``content_type``: ``'full'`` (changed files), ``'structure'``
    (key files), or ``'name_only'`` (low-priority files).
    """
    _STRUCTURE_THRESHOLD = 2.0
    result = []
    for file_info in selected:
        is_changed = file_info.get('changed', False)
        priority = file_info.get('priority', _STRUCTURE_THRESHOLD)

        if is_changed:
            content = _get_file_raw_content(file_info['path'])
            content_type = 'full'
        elif priority >= _STRUCTURE_THRESHOLD:
            content = _get_file_structure(file_info['path'])
            content_type = 'structure'
        else:
            content = ''
            content_type = 'name_only'

        result.append({
            'file': file_info['relative'],
            'changed': is_changed,
            'content_type': content_type,
            'content': content,
        })
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


def _collect_candidates(
    path: Path,
    focus: Optional[str],
    changed_files: Optional[Set[str]] = None,
    fan_in_scores: Optional[Dict[str, int]] = None,
    graph_relevance_scores: Optional[Dict[str, float]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Collect and score candidate files for the pack."""
    candidates: List[Dict[str, Any]] = []

    for f in _walk_files(path, exclude_patterns=exclude_patterns):
        # Skip near-empty __init__.py files — they're almost always re-export
        # stubs and waste token budget without adding understanding
        if f.name == '__init__.py' and f.stat().st_size < 500:
            continue

        rel = f.relative_to(path)
        stat = f.stat()
        size_chars = stat.st_size
        tokens_approx = size_chars // _APPROX_CHARS_PER_TOKEN
        lines = _count_lines(f)

        is_changed = bool(changed_files and str(f.resolve()) in changed_files)
        fan_in = (fan_in_scores or {}).get(str(f.resolve()), 0)
        graph_relevance = (graph_relevance_scores or {}).get(str(f.resolve()), 0.0)
        priority = _compute_priority(
            f, rel, focus, is_changed=is_changed, fan_in=fan_in,
            graph_relevance=graph_relevance,
        )

        candidates.append({
            'path': str(f),
            'relative': to_posix(rel),
            'priority': priority,
            'tokens_approx': tokens_approx,
            'lines': lines,
            'mtime': stat.st_mtime,
            'size': stat.st_size,
            'changed': is_changed,
            'fan_in': fan_in,
            'graph_relevance': graph_relevance,
        })

    # Sort: priority descending, then mtime descending
    candidates.sort(key=lambda c: (-c['priority'], -c['mtime']))
    return candidates


def _compute_priority(
    path: Path,
    rel: Path,
    focus: Optional[str],
    is_changed: bool = False,
    fan_in: int = 0,
    graph_relevance: float = 0.0,
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
    # not a repeated convention, so they keep the full bonus unconditionally.
    if name in _ENTRY_POINT_CONFIG_FILES:
        score += 10.0
    elif name in _ENTRY_POINT_PATTERNS:
        file_size = path.stat().st_size
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
    if name == '__init__.py' and path.stat().st_size > 2000:
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

    # Penalize test/vendor/docs files. Directory markers are matched as whole
    # path components (via rel_parts) so a *top-level* tests/ or vendor/ dir is
    # penalized the same as a nested one — BACK-526: the old '/tests/' substring
    # check missed a path starting with 'tests/', letting test-model DTOs under
    # a top-level tests/ tree surface in the "Key modules" tier.
    if rel_parts & {'test', 'tests', 'vendor', 'docs', '__pycache__', 'node_modules'}:
        score -= 3.0
    for penalty in ('test_', '_test', '/.'):
        if penalty in rel_str:
            score -= 3.0
            break

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
        and name not in _ENTRY_POINT_PATTERNS
        and name not in _ENTRY_POINT_CONFIG_FILES
    ):
        score -= 2.0

    # Penalize very large files (noisy)
    if path.stat().st_size > 50_000:
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
    skipped = 0

    for c in candidates:
        if budget_tokens is not None:
            if used_tokens + c['tokens_approx'] > budget_tokens:
                skipped += 1
                continue
            used_tokens += c['tokens_approx']

        if budget_lines is not None:
            if used_lines + c['lines'] > budget_lines:
                skipped += 1
                continue

        used_lines += c['lines']
        selected.append(c)

    meta = {
        'total_candidates': len(candidates),
        'selected': len(selected),
        'skipped': skipped,
        'used_tokens_approx': used_tokens,
        'used_lines': used_lines,
        'budget_tokens': budget_tokens,
        'budget_lines': budget_lines,
    }
    return selected, meta


def _walk_files(
    path: Path, exclude_patterns: Optional[List[str]] = None,
) -> Generator[Path, None, None]:
    """Yield code/config files under *path* (respects common ignores).

    BACK-1196: *exclude_patterns* (from ?exclude=, the inverse of ?focus=)
    lets a caller drop a whole area (fixtures, generated code, a vendored
    subtree) from candidacy entirely, rather than only being able to boost
    relevance elsewhere. Matched via the same should_skip_file() mechanism
    overview://'s ?exclude= already uses (BACK-1042), for consistent
    pattern semantics across adapters.
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

    should_skip_file = None
    if exclude_patterns:
        from ..cli.file_checker import should_skip_file  # deferred: cli cycle

    if path.is_file():
        yield path
        return

    for item in path.rglob('*'):
        if item.is_dir():
            continue
        # Skip hidden/ignored dirs (BACK-552: env/venv/build/dist checked
        # against actual directory content, not just bare name)
        accumulated = path
        skip = False
        for part in item.relative_to(path).parts[:-1]:
            if part.startswith('.') or is_skippable_dir(accumulated, part):
                skip = True
                break
            accumulated = accumulated / part
        if skip:
            continue
        rel = item.relative_to(path)
        if should_skip_file is not None and should_skip_file(rel, exclude_patterns):
            continue
        # Include root config files
        if item.parent == path and item.name in _ROOT_FILES:
            yield item
            continue
        # Include code files by extension
        if item.suffix.lower() in _CODE_EXTENSIONS:
            yield item


def _count_lines(path: Path) -> int:
    """Count lines in a file."""
    try:
        return path.read_text(encoding='utf-8', errors='ignore').count('\n')
    except Exception:
        # Line count feeds priority scoring only; an unreadable file just
        # sorts as if it were empty rather than blocking the pack.
        return 0


def _render_architecture_brief(selected: List[Dict[str, Any]]) -> None:
    """Print a concise architecture hint derived from fan-in and priority."""
    entry_points = [
        f['relative'] for f in selected
        if not f.get('changed') and f.get('priority', 0) >= 8
    ]
    core = sorted(
        [f for f in selected if f.get('fan_in', 0) >= 5],
        key=lambda f: -f.get('fan_in', 0),
    )[:5]

    print('── Architecture Hint ──')
    if entry_points:
        print(f"Entry points:      {', '.join(entry_points)}")
    if core:
        abstractions = '  '.join(
            f"{f['relative']}({f['fan_in']})" for f in core
        )
        print(f"Core abstractions: {abstractions}")
    if not entry_points and not core and selected:
        top = sorted(selected, key=lambda f: -f.get('priority', 0))[:3]
        print(f"Top files:         {', '.join(f['relative'] for f in top)}")
    print()


def _print_pack_header(
    path: Path,
    meta: Dict[str, Any],
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
) -> None:
    budget_desc = (f"~{budget_tokens} tokens" if budget_tokens else f"{budget_lines} lines")
    since = meta.get('since')
    since_desc = f"  [since {since}]" if since else ""
    print(f"Pack: {path}  [{budget_desc} budget]{since_desc}")
    if since:
        print(f"Changed files:  {meta.get('changed_files_count', 0)} (boosted to top priority)")
    print(f"Selected {meta['selected']} of {meta['total_candidates']} files "
          f"(~{meta['used_tokens_approx']} tokens, {meta['used_lines']} lines)")
    print()


def _print_pack_file_groups(
    selected: List[Dict[str, Any]],
    meta: Dict[str, Any],
    verbose: bool,
    architecture: bool,
) -> None:
    since = meta.get('since')
    if architecture:
        _render_architecture_brief(selected)

    changed = [f for f in selected if f.get('changed')]
    high = [f for f in selected if not f.get('changed') and f['priority'] >= 8]
    medium = [f for f in selected if not f.get('changed') and 2 <= f['priority'] < 8]
    low = [f for f in selected if not f.get('changed') and f['priority'] < 2]

    for label, group in [
        (f"── Changed files (since {since}) ──", changed),
        ("── Entry points / focus files ──", high),
        ("── Key modules ──", medium),
        ("── Other files ──", low),
    ]:
        if group:
            print(label)
            for f in group:
                _print_file_line(f, verbose)
            print()


def _render_pack(
    path: Path,
    selected: List[Dict[str, Any]],
    meta: Dict[str, Any],
    verbose: bool,
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
    architecture: bool = False,
) -> None:
    """Render pack output as text."""
    _print_pack_header(path, meta, budget_tokens, budget_lines)
    if not selected:
        print("No files fit within budget.")
        return
    _print_pack_file_groups(selected, meta, verbose, architecture)
    if meta['skipped'] > 0:
        print(f"[{meta['skipped']} files excluded — exceeded budget]")


def _print_file_line(f: Dict[str, Any], verbose: bool) -> None:
    """Print one file entry."""
    rel = f['relative']
    tokens = f['tokens_approx']
    lines = f['lines']
    if verbose:
        print(f"  {rel:50} {tokens:5} tokens  {lines:4} lines")
    else:
        print(f"  {rel}")


def _format_file_line(f: Dict[str, Any]) -> str:
    """Format one file entry as a string (verbose form, for MCP / string consumers)."""
    return f"  {f['relative']:50} {f['tokens_approx']:5} tokens  {f['lines']:4} lines"


def _format_pack_header(
    path: Path,
    meta: Dict[str, Any],
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
    since_error: Optional[str],
) -> List[str]:
    """Format the pack header (budget + since + selected counts) as lines."""
    since_val = meta.get('since')
    budget_desc = f"~{budget_tokens} tokens" if budget_tokens else f"{budget_lines} lines"
    since_desc = f"  [since {since_val}]" if since_val else ""
    lines = [f"Pack: {path}  [{budget_desc} budget]{since_desc}"]
    if since_val:
        lines.append(f"Changed files:  {meta.get('changed_files_count', 0)} (boosted to top priority)")
    if since_error:
        lines.append(f"Warning: --since: {since_error}")
    lines.append(
        f"Selected {meta['selected']} of {meta['total_candidates']} files "
        f"(~{meta['used_tokens_approx']} tokens, {meta['used_lines']} lines)"
    )
    lines.append("")
    return lines


def _format_pack_file_groups(selected: List[Dict[str, Any]], meta: Dict[str, Any]) -> List[str]:
    """Format the tiered file listing (changed/high/medium/low) as lines."""
    since_val = meta.get('since')
    groups = [
        (f"── Changed files (since {since_val}) ──",
         [f for f in selected if f.get('changed')]),
        ("── Entry points / focus files ──",
         [f for f in selected if not f.get('changed') and f['priority'] >= 8]),
        ("── Key modules ──",
         [f for f in selected if not f.get('changed') and 2 <= f['priority'] < 8]),
        ("── Other files ──",
         [f for f in selected if not f.get('changed') and f['priority'] < 2]),
    ]
    lines: List[str] = []
    for header, files in groups:
        if files:
            lines.append(header)
            lines.extend(_format_file_line(f) for f in files)
            lines.append("")
    if meta['skipped'] > 0:
        lines.append(f"[{meta['skipped']} files excluded — exceeded budget]")
    return lines


def _format_pack_content(selected: List[Dict[str, Any]]) -> List[str]:
    """Format the per-file content section (changed=full, key=structure, low=names)."""
    content_data = _collect_file_contents(selected)
    lines = [
        "",
        "━" * 70,
        "CONTENT  (changed=full · key files=structure · low priority=names)",
        "━" * 70,
    ]
    name_only: List[str] = []
    for entry in content_data:
        if entry['content_type'] == 'name_only':
            name_only.append(entry['file'])
            continue
        marker = "  ◀ CHANGED (full content)" if entry['content_type'] == 'full' else ""
        lines.append(f"\n── {entry['file']}{marker} ──")
        lines.append(entry['content'].rstrip() if entry['content'].strip() else "[unreadable]")
    if name_only:
        lines.append("\n── Low-priority files (selected, structure omitted) ──")
        lines.extend(f"  {f}" for f in name_only)
    return lines


def _format_pack_result(
    path: Path,
    selected: List[Dict[str, Any]],
    meta: Dict[str, Any],
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
    since_error: Optional[str] = None,
    content: bool = True,
) -> str:
    """Render pack output as a string (for MCP / non-stdout consumers).

    Unlike :func:`_render_pack` (which prints), this returns the full result
    as a single string suitable for returning from an MCP tool call.
    """
    lines = _format_pack_header(path, meta, budget_tokens, budget_lines, since_error)
    if not selected:
        lines.append("No files fit within budget.")
    else:
        lines.extend(_format_pack_file_groups(selected, meta))
    if content and selected:
        lines.extend(_format_pack_content(selected))
    return "\n".join(lines)


class PackRenderer:
    """Renderer for pack:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text',
                          verbose: bool = False, architecture: bool = False,
                          content: bool = False) -> None:
        if format == 'json':
            print_json_result(result)
            return
        path = Path(result['path'])
        selected = result['files']
        meta = result['meta']
        _render_pack(path, selected, meta, verbose,
                     meta.get('budget_tokens'), meta.get('budget_lines'),
                     architecture=architecture)
        if content:
            _emit_content_section(selected)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error building pack: {error}")


@register_adapter('pack')
@register_renderer(PackRenderer)
class PackAdapter(ResourceAdapter):
    """Adapter curating a token-budgeted context snapshot for LLM consumption:
    ranks candidate files by priority (entry points, fan-in, focus/graph
    relevance, changed-since-ref) and selects as many as fit the budget."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
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
            ],
            'notes': [
                'Token counts are approximate (chars / 4), not a real tokenizer.',
            ],
            'see_also': [
                'reveal pack <path> - CLI subcommand form',
                'reveal_pack MCP tool - same ranking, MCP-native',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'pack',
            'description': 'Token-budgeted context snapshot: ranked file selection for LLM consumption',
            'uri_syntax': 'pack://<path>?budget=2000&focus=auth&since=main&content=true&architecture=true',
            'query_params': {
                'budget': {'type': 'string', 'description': 'Token or line budget (e.g. 2000, 500-lines)', 'examples': ['budget=4000', 'budget=500-lines']},
                'focus': {'type': 'string', 'description': 'Emphasize files matching this name pattern', 'examples': ['focus=auth']},
                'exclude': {'type': 'string', 'description': 'Comma-separated patterns to drop from candidacy entirely (inverse of focus=)', 'examples': ['exclude=spec/*,vendor/*']},
                'since': {'type': 'string', 'description': 'Git ref to diff against; changed files boosted to top priority', 'examples': ['since=main']},
                'content': {'type': 'boolean', 'description': 'Include tiered file content (full/structure/name_only)', 'examples': ['content=true']},
                'architecture': {'type': 'boolean', 'description': 'Boost high fan-in files; include an architecture hint', 'examples': ['architecture=true']},
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

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        # BACK-1180: two compounding bugs made ?budget=0 silently fall back
        # to the 2000 default instead of being honored (0 = select nothing).
        # 1. 'or' treats a falsy coerced value as absent (BACK-985 shape).
        # 2. query_parser.coerce_value() coerces the literal strings '0'/'1'
        #    to bool False/True regardless of the field's real type — so
        #    budget=0 arrives here as `False`, and str(False) == 'False'
        #    fails _parse_budget's int() and falls back to 2000 too.
        _budget_param = self.query_params.get('budget')
        if _budget_param is None:
            budget_str = '2000'
        elif isinstance(_budget_param, bool):
            budget_str = str(int(_budget_param))
        else:
            budget_str = str(_budget_param)
        focus = self.query_params.get('focus') or None
        since = self.query_params.get('since') or None
        emit_content = str(self.query_params.get('content', False)).lower() == 'true'
        architecture = str(self.query_params.get('architecture', False)).lower() == 'true'
        # BACK-1196: ?exclude= is the inverse of ?focus= — drop a whole area
        # (fixtures, generated code, a vendored subtree) from candidacy
        # entirely, comma-separated, same format as overview://'s ?exclude=.
        exclude_param = self.query_params.get('exclude')
        exclude_patterns = (
            [p for p in str(exclude_param).split(',') if p] if exclude_param else None
        )

        budget_tokens, budget_lines = _parse_budget(budget_str)

        changed_files: Set[str] = set()
        if since:
            changed_files, self.since_error = _get_changed_files(path, since)

        fan_in_scores = _fetch_fan_in(path) if architecture else None
        graph_relevance_scores = _compute_graph_relevance(path, focus) if focus else {}

        if not architecture and not focus:
            self.relevance_warning = (
                "fan-in and graph-relevance signals were not computed (pass "
                "--architecture and/or --focus to enable) -- files are "
                "ranked by filename/entry-point heuristics and recency only"
            )

        candidates = _collect_candidates(
            path, focus, changed_files, fan_in_scores=fan_in_scores,
            graph_relevance_scores=graph_relevance_scores,
            exclude_patterns=exclude_patterns,
        )
        selected, meta = _apply_budget(candidates, budget_tokens, budget_lines, path)
        if since:
            meta['since'] = since
            meta['changed_files_count'] = len(changed_files)
        if self.relevance_warning:
            meta['relevance_warning'] = self.relevance_warning

        report: Dict[str, Any] = {
            'path': str(path),
            'budget': budget_str,
            'since': since,
            'meta': meta,
            'files': selected,
        }
        if emit_content:
            report['content'] = _collect_file_contents(selected)

        return ResultBuilder.create(
            result_type='pack',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
        )
