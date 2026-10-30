#!/usr/bin/env python3
"""Pinned-corpus recall gate: independent import or callers oracles on pinned corpora.

Each manifest entry with a ``recall:`` block names an oracle from scripts/recall_oracles.py
(a real compiler, the language's own parser, or a from-scratch resolution rule; never
Reveal's extractor or resolver). The gate checks the corpus is at its pinned commit, builds
the oracle over the configured importer population, builds Reveal's dependency graph over
the same scan root, and compares fan-in edges for every oracle target. Recall or precision
below the committed baseline, a changed population, an oracle or Reveal side that measured
nothing, or a missing corpus all fail; nothing is reported as a clean zero.
The default signal is imports; --signal calls runs the separate pinned Python caller baseline, locally or in the scheduled workflow.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.metadata
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from recall_oracles import ORACLES, Scope, tracked_files, test_importers, build_python_calls_oracle
from reveal.main import main as reveal_main
from reveal.utils.request_cache import reset_request_caches
from reveal import __version__

MANIFEST = Path(__file__).resolve().parent.parent / 'tests/corpus/manifest.yaml'
BASELINE = MANIFEST.with_name('recall_baseline.json')
# Fields whose change means the measured population moved: review the baseline, never auto-accept.
POPULATION_FIELDS = ('oracle', 'sha', 'targets', 'oracle_edges', 'coverage')


# The one parameter combination the import oracles define truth for, and that the importer views apply by default:
# every static edge, function-level and tests included, TYPE_CHECKING excluded (BACK-2077).
SCORED_RULE = {'lazy': 'include', 'tests': 'included', 'type_checking': 'excluded'}
# The combinations the engine states but this gate cannot score everywhere (BACK-2062). &lazy=exclude and
# &lazy=only are scored for the populations whose oracle labels function-level imports (python-ast, typescript-compiler; LAZY_MODES).
LAZY_MODES = ('exclude', 'only')
_LAZY_DECLINED = ('scored for python-ast and typescript-compiler populations (the oracles label function-level imports). '
                  'Declined elsewhere: rust-use is a regex that cannot tell a fn-local use '
                  '(BACK-2079); C, C++, Go and Java have no function-scope import')
DECLINED = (
    {'combination': 'lazy=exclude', 'reason': _LAZY_DECLINED},
    {'combination': 'lazy=only', 'reason': 'as lazy=exclude'},
    {'combination': 'tests=exclude', 'reason': 'scored at lazy=include for populations with reviewed '
     'test_importer_dirs; declined elsewhere without independent corpus test labels'},
    {'combination': 'tests=exclude with lazy=exclude/only', 'reason': 'cross-product not qualified'},
)


@contextlib.contextmanager
def _engine_uncached():
    """Score the engine, not a stored answer: imports:// keeps its graph on disk, so a second measurement in
    the same process (or on a runner with a warm cache) would read the first one's answer and miss a loss
    injected or introduced between them. Cache correctness is BACK-2081's differential test, not this gate's."""
    before = os.environ.get('REVEAL_DISK_CACHE')
    os.environ['REVEAL_DISK_CACHE'] = '0'
    try:
        yield
    finally:
        if before is None:
            os.environ.pop('REVEAL_DISK_CACHE', None)
        else:
            os.environ['REVEAL_DISK_CACHE'] = before


def _cli_json(uri: str, label: str, *, incomplete_ok: bool = False) -> dict[str, Any]:
    """One request through ``reveal.main.main`` with the argv a user would type, read back as JSON.

    Flag routing, the project-root choice, the rendered path spelling and the disclosures are the
    CLI's own; no adapter internals are read. A failed answer raises instead of becoming a smaller
    truth (BACK-2062).
    """
    scheme = uri.split('://', 1)[0]
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            reveal_main(['reveal', uri, '--format', 'json'])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 0
    try:
        result = json.loads(out.getvalue())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'{scheme}:// printed no JSON for {label} (exit {code}): {err.getvalue()[:200]}') from exc
    # Exit 3 is 'complete answer, incomplete analysis' (a file parsed with errors): the caller qualifies it.
    if (code and not (incomplete_ok and code == 3)) or result.get('error'):
        raise RuntimeError(f'{scheme}:// failed for {label} (exit {code}): {result.get("error") or err.getvalue()[:200]}')
    return result


def _importers_request(target: Path, scan: Path, cap: int | None, lazy: str = 'include',
                       tests: str = 'include') -> dict[str, Any]:
    """One ``imports://<target>?importers`` request at the scan root; a capped scan raises like any
    other failed answer. ``cap`` is the corpus's own ``scan_file_cap``, else the engine's default."""
    query = f'importers&root={urllib.parse.quote(scan.as_posix(), safe="/:")}' + (f'&max_files={cap}' if cap else '')
    if lazy != 'include':
        query += f'&lazy={lazy}'
    if tests != 'include':
        query += f'&tests={tests}'
    with _engine_uncached():
        result = _cli_json(f'imports://{target.as_posix()}?{query}', target.name, incomplete_ok=True)
    if (result.get('metadata', {}).get('scan_budget') or {}).get('capped'):
        raise RuntimeError('Reveal scan was capped; measurement unavailable')
    rule = result.get('edge_rule') or {}
    scored = {**SCORED_RULE, 'lazy': lazy, 'tests': 'importers_not_counted' if tests == 'exclude' else 'included'}
    applied = {key: rule.get(key) for key in scored}
    if applied != scored:
        shown = ', '.join(f'{key}={value!r}' for key, value in applied.items() if value != scored[key])
        raise RuntimeError(f'imports:// answered under rule {shown}; the gate scores {scored}')
    _edge_rule(result)  # Reject lost policy evidence before accepting any scores.
    return result


def _edge_rule(result: dict[str, Any]) -> dict[str, Any]:
    """Retain the engine's rule and require its existing lexical test-scope evidence."""
    rule = result['edge_rule']
    scope = rule.get('test_scope')
    if (not isinstance(scope, dict)
            or any(not isinstance(scope.get(key), str) or not scope[key]
                   for key in ('anchor', 'source', 'basis'))
            or scope.get('rule') != 'is_test_path'
            or not isinstance(scope.get('include_anchor_name'), bool)):
        raise RuntimeError('imports:// carries missing or malformed test_scope; measurement unavailable')
    return {**{key: rule.get(key) for key in (*SCORED_RULE, 'scope', 'unclassified_languages')},
            'test_scope': copy.deepcopy(scope)}


def _partial_files(result: dict[str, Any]) -> int:
    """Files parsed with errors, from the metadata ``imports://`` prints them from (failed minus lost, as
    its own summary computes it). A file lost to a dead worker or unreadable is not a partial parse:
    the answer is smaller than the tree's, so the gate refuses it."""
    metadata = result.get('metadata') or {}
    lost, failed = metadata.get('files_lost_count'), metadata.get('files_failed_count')
    if not isinstance(lost, int) or not isinstance(failed, int):
        raise RuntimeError('imports:// answer carries no files_failed_count/files_lost_count; cannot qualify it')
    if lost:
        raise RuntimeError(f'imports:// lost {lost} file(s) from its answer; measurement unavailable')
    return failed


def rendered_dependents(scan: Path, target: Path, cap: int | None) -> dict[str, Any]:
    """Importers of one file as ``imports://<file>?importers`` prints them: the package view Go needs, where
    an import names a directory. It builds the whole graph per request, so use it only where the
    directory form below cannot answer."""
    result = _importers_request(target, scan, cap)
    importers = result['importers']
    if len(importers) != result['count']:
        raise RuntimeError(f'imports:// answer truncated for {target.name}: {len(importers)} of {result["count"]} shown')
    return {'importers': {Path(os.path.normpath(target.parent / row['file'])) for row in importers},
            'partial_files': _partial_files(result), 'edge_rule': _edge_rule(result)}


def rendered_reverse_graph(scan: Path, cap: int | None, lazy: str = 'include',
                           tests: str = 'include') -> dict[str, Any]:
    """Every module's importers from ONE ``imports://<scan dir>?importers`` request (the importer summary).

    ``imports://<file>?importers`` rebuilds the full import graph per request (4837 files, 10-28 s each
    on the Java corpus), so a per-target gate would take hours; the directory summary lists every
    module with at least one importer, sorted, in a single answer.
    """
    result = _importers_request(scan, scan, cap, lazy, tests)
    entries = result['entries']
    if len(entries) != result['total']:
        raise RuntimeError(f'imports:// summary truncated: {len(entries)} of {result["total"]} modules shown')
    return {'by_target': {Path(os.path.normpath(scan / e['file'])): {Path(os.path.normpath(scan / i)) for i in e['importers']}
                          for e in entries},
            'partial_files': _partial_files(result), 'edge_rule': _edge_rule(result)}


def corpus_key(entry: dict) -> str:
    return entry.get('id', entry['language'])


def measure(entry: dict, root: Path) -> dict[str, Any]:
    head = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True,
                          capture_output=True, text=True, encoding='utf-8', timeout=30).stdout.strip()
    if not entry.get('sha') or head != entry['sha']:
        raise RuntimeError(f'Corpus pin mismatch: expected {entry.get("sha")}, got {head}')
    config = entry['recall']
    name = config.get('oracle')
    if name not in ORACLES:
        raise RuntimeError(f'Unknown recall oracle {name!r}; expected one of {sorted(ORACLES)}')
    oracle = ORACLES[name]
    scan = (root / config.get('scan_root', '.')).resolve()
    if not scan.is_dir() or not scan.is_relative_to(root):
        raise RuntimeError(f'scan_root {config.get("scan_root")!r} is not a directory in the corpus')
    importers = tracked_files(root, config['importer_dirs'], oracle.suffixes)
    edges, coverage = oracle.build(Scope(root, scan, importers, config))
    if not edges or not importers or not coverage.get('files'):
        raise RuntimeError('Oracle produced zero rows/files; measurement unavailable')
    # The corpus's own file cap (&max_files=), else the engine's default: the gate scores what a user gets.
    cap = config.get('scan_file_cap')
    if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0):
        raise RuntimeError('scan_file_cap must be a positive integer')
    excluded_suffixes = tuple(config.get('exclude_importer_suffixes', []))
    population = {p for p in importers if not excluded_suffixes or not p.name.endswith(excluded_suffixes)}
    reset_request_caches()
    # Go imports name packages, so its per-file answer is the package view of imports://<file>?importers.
    graph = None if name == 'go-toolchain' else rendered_reverse_graph(scan, cap)
    meta: dict[str, Any] = {'partial_files': 0, 'edge_rule': {}}

    def importers_of(target: str) -> set[Path]:
        if graph is None:
            view = rendered_dependents(scan, root / target, cap)
            meta.update(partial_files=view['partial_files'], edge_rule=view['edge_rule'])
            return view['importers']
        meta.update(partial_files=graph['partial_files'], edge_rule=graph['edge_rule'])
        return graph['by_target'].get(root / target, set())

    hit, expected, extra, differences = _score(edges, importers_of, root, population)
    if not hit:
        raise RuntimeError('Reveal found zero oracle edges; positive control failed')
    result = {'oracle': name, 'sha': head, 'targets': len(edges), 'oracle_edges': expected, 'hit_edges': hit,
              'extra_edges': extra, 'recall': hit / expected, 'precision': hit / (hit + extra),
              'coverage': coverage, 'partial_files': meta['partial_files'], 'edge_rule': meta['edge_rule'],
              'differences': differences}
    if oracle.lazy_only is not None and graph is not None:
        result['lazy'] = _measure_lazy(oracle, Scope(root, scan, importers, config), edges, root, scan, cap, population)
    if 'test_importer_dirs' in config:
        if graph is None:
            raise RuntimeError('Test exclusion scoring requires the directory importer view')
        result['tests'] = {'exclude': _measure_tests(Scope(root, scan, importers, config), edges, cap, population)}
    return result


def _score(edges: dict[str, list[str]], importers_of, root: Path, population: set[Path]):
    """(hit, expected, extra, differences) of ``importers_of(target)`` against the oracle's importers per target."""
    hit = expected = extra = 0
    differences = []
    for target, truth_list in edges.items():
        truth = set(truth_list)
        found = {p.relative_to(root).as_posix() for p in importers_of(target) if p in population}
        matched, missed, surplus = truth & found, truth - found, found - truth
        hit += len(matched)
        expected += len(truth)
        extra += len(surplus)
        if missed or surplus:
            differences.append({'target': target, 'missed': sorted(missed), 'extra': sorted(surplus)})
    return hit, expected, extra, differences


def _measure_lazy(oracle, scope: Scope, edges: dict[str, list[str]], root: Path, scan: Path, cap: int | None,
                  population: set[Path]) -> dict[str, Any]:
    """Score ``&lazy=exclude`` and ``&lazy=only`` as rendered. An edge is function-level only when every import
    behind it is (the engine's ``is_lazy_edge``), so the oracle's edges split into two disjoint sets. Every oracle
    target is scored in each mode, including those whose truth is empty there, so an importer the engine lists
    in the wrong view counts as extra."""
    lazy_edges = oracle.lazy_only(scope)
    modes: dict[str, Any] = {}
    for mode in LAZY_MODES:
        truth = {t: sorted(set(importers) - set(lazy_edges.get(t, ())) if mode == 'exclude'
                           else set(lazy_edges.get(t, ())))
                 for t, importers in edges.items()}
        graph = rendered_reverse_graph(scan, cap, mode)
        hit, expected, extra, differences = _score(truth, lambda t: graph['by_target'].get(root / t, set()), root, population)
        if expected and not hit:
            raise RuntimeError(f'lazy={mode}: reveal found zero oracle edges; positive control failed')
        # A population with no edge in this view (a corpus without function-level imports) has nothing to recall:
        # recall is None, and the importers reveal lists there still count as extra.
        modes[mode] = {'targets': sum(1 for v in truth.values() if v), 'oracle_edges': expected, 'hit_edges': hit,
                       'extra_edges': extra, 'recall': hit / expected if expected else None,
                       'precision': hit / (hit + extra) if hit + extra else None,
                       'partial_files': graph['partial_files'], 'edge_rule': graph['edge_rule'],
                       'differences': differences}
    return modes


def _measure_tests(scope: Scope, edges: dict[str, list[str]], cap: int | None,
                   population: set[Path]) -> dict[str, Any]:
    """Remove independently labelled test importers, retaining every target for extra-edge controls."""
    labels = test_importers(scope)
    truth = {target: sorted(set(importers) - labels) for target, importers in edges.items()}
    removed = sum(len(set(importers) & labels) for importers in edges.values())
    if not removed:
        raise RuntimeError('Declared test population has zero oracle edges; exclusion control is vacuous')
    graph = rendered_reverse_graph(scope.scan, cap, tests='exclude')
    hit, expected, extra, differences = _score(
        truth, lambda target: graph['by_target'].get(scope.root / target, set()), scope.root, population)
    if expected and not hit:
        raise RuntimeError('tests=exclude: reveal found zero oracle edges; positive control failed')
    return {'targets': sum(bool(importers) for importers in truth.values()),
            'oracle_edges': expected, 'hit_edges': hit, 'extra_edges': extra,
            'recall': hit / expected if expected else None,
            'precision': hit / (hit + extra) if hit + extra else None,
            'partial_files': graph['partial_files'], 'edge_rule': graph['edge_rule'],
            'test_population': {'directories': scope.config['test_importer_dirs'],
                                'files': len(labels), 'edges': removed},
            'differences': differences}


def rendered_callers(scan: Path, target: str) -> list[dict[str, Any]]:
    """Callers of one name as ``calls://<scan>?callers=<name>`` prints them; a cut answer raises."""
    result = _cli_json(f'calls://{scan.as_posix()}?callers={urllib.parse.quote(target, safe="")}', target)
    if result.get('meta', {}).get('errors'):
        raise RuntimeError(f'calls:// reported errors for {target}: {result["meta"]["errors"][:3]}')
    rows = [row for level in result['levels'] for row in level['callers']]
    if len(rows) != result['total_callers']:
        raise RuntimeError(f'calls:// answer truncated for {target}: {len(rows)} of {result["total_callers"]} shown')
    return rows


def measure_calls(entry: dict, root: Path) -> dict[str, Any]:
    """Measure the public callers answer (``calls://?callers=``) against independent Python AST."""
    head = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True,
                          capture_output=True, text=True, encoding='utf-8', timeout=30).stdout.strip()
    if head != entry['sha']:
        raise RuntimeError('Call corpus pin mismatch')
    config = entry['call_recall']
    if config.get('oracle', 'python-ast-callers') != 'python-ast-callers':
        raise RuntimeError('Unknown call oracle')
    scan = (root / config['scan_root']).resolve()
    if not scan.is_dir() or not scan.is_relative_to(root):
        raise RuntimeError('Call scan root is missing or escapes the corpus')
    files = tracked_files(root, config['importer_dirs'], frozenset({'.py'}))
    if not files or any(not path.is_relative_to(scan) for path in files):
        raise RuntimeError('Call population is empty or outside scan root')
    edges, coverage = build_python_calls_oracle(Scope(root, scan, files, config))
    expected = sum(map(len, edges.values()))
    if not expected:
        raise RuntimeError('Call oracle produced zero claims')
    hit = extra = 0
    differences = []
    reset_request_caches()
    for target, truth_list in edges.items():
        truth = set(truth_list)
        found = {f"{Path(row['file']).relative_to(root).as_posix()}::{row['caller']}"
                 for row in rendered_callers(scan, target)
                 if row.get('caller_kind') != 'module' and Path(row['file']) in files}
        matched, missed, surplus = truth & found, truth - found, found - truth
        hit += len(matched)
        extra += len(surplus)
        if missed or surplus:
            differences.append({'target': target, 'missed': sorted(missed), 'extra': sorted(surplus)})
    if not hit:
        raise RuntimeError('Reveal found zero call claims')
    return {'oracle': 'python-ast-callers', 'sha': head, 'targets': len(edges),
            'oracle_edges': expected, 'hit_edges': hit, 'extra_edges': extra,
            'recall': hit / expected, 'precision': hit / (hit + extra),
            'coverage': coverage, 'differences': differences}


def regressions(current: dict, baseline: dict, notes: list[str] | None = None) -> list[str]:
    """Failures against the baseline; ``notes`` collects comparisons that could not be made (not failures)."""
    failures = [f'{key}: baseline missing; review required' for key in sorted(current.keys() - baseline.keys())]
    if not baseline:
        return failures or ['Baseline is empty; measurement unavailable']
    for key, reference in baseline.items():
        measured = current.get(key)
        if not measured:
            failures.append(f'{key}: measurement missing')
            continue
        for field in POPULATION_FIELDS:
            if measured.get(field) != reference.get(field):
                failures.append(f'{key}: oracle population/pin changed ({field}); baseline review required')
        if (measured.get('extra_edges') != reference.get('extra_edges')
                or extra_identities(measured) != extra_identities(reference)):
            failures.append(f'{key}: extra-edge population changed; baseline review required')
        for field in ('recall', 'precision'):
            if measured[field] + 1e-12 < reference[field]:
                failures.append(f'{key}: {field} dropped {reference[field]:.6%} -> {measured[field]:.6%}')
        _compare_partial_files(key, measured, reference, failures, notes)
        for dimension in ('lazy', 'tests'):
            _compare_modes(key, dimension, measured.get(dimension) or {}, reference.get(dimension) or {}, failures, notes)
    return failures


def _compare_modes(key: str, dimension: str, measured: dict, reference: dict, failures: list[str],
                   notes: list[str] | None = None) -> None:
    """The all-edges checks per parameter view; a new or vanished view requires review."""
    for mode in sorted(measured.keys() - reference.keys()):
        failures.append(f'{key}: {dimension}={mode} baseline missing; review required')
    for mode, ref in reference.items():
        row = measured.get(mode)
        if not row:
            failures.append(f'{key}: {dimension}={mode} measurement missing')
            continue
        for field in ('targets', 'oracle_edges', 'test_population'):
            if row.get(field) != ref.get(field):
                failures.append(f'{key}: {dimension}={mode} oracle population changed ({field}); baseline review required')
        if row.get('extra_edges') != ref.get('extra_edges') or extra_identities(row) != extra_identities(ref):
            failures.append(f'{key}: {dimension}={mode} extra-edge population changed; baseline review required')
        for field in ('recall', 'precision'):
            if None not in (row[field], ref[field]) and row[field] + 1e-12 < ref[field]:
                failures.append(f'{key}: {dimension}={mode} {field} dropped {ref[field]:.6%} -> {row[field]:.6%}')
        _compare_partial_files(f'{key}: {dimension}={mode}', row, ref, failures, notes)


def _compare_partial_files(key: str, measured: dict, reference: dict, failures: list[str],
                           notes: list[str] | None) -> None:
    """More partially parsed files than the baseline is a regression; fewer is not. A side without the
    field (calls measurements, baselines written before it existed) is disclosed as not compared."""
    now, before = measured.get('partial_files'), reference.get('partial_files')
    if now is None and before is None:
        return
    if now is None or before is None:
        if notes is not None:
            side = 'baseline' if before is None else 'measurement'
            notes.append(f'{key}: partial_files not compared ({side} has no partial_files)')
    elif now > before:
        failures.append(f'{key}: partial_files rose {before} -> {now}; more files parse only partially')


def extra_identities(measurement: dict) -> set:
    """Reviewed extras are identities, not interchangeable errors of equal count."""
    return {(row['target'], source) for row in measurement.get('differences', [])
            for source in row.get('extra', [])}


def _selected(manifest: dict, wanted: list[str], signal: str = "imports") -> tuple[list[dict], list[str]]:
    field = 'call_recall' if signal == 'calls' else 'recall'
    entries = [e for e in manifest['corpora'] if field in e]
    if not wanted:
        return entries, []
    keys = {corpus_key(e) for e in entries}
    return [e for e in entries if corpus_key(e) in wanted], [f'{w}: no recall entry with that id'
                                                             for w in wanted if w not in keys]


def _read_baseline(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def implementation_identity() -> dict[str, str]:
    """Identify local measurements even when the checkout has uncommitted work."""
    repo = Path(__file__).resolve().parent.parent
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              capture_output=True, timeout=30).stdout
    untracked = hashlib.sha256()
    for raw in sorted(git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0')):
        if raw:
            untracked.update(raw)
            untracked.update((repo / raw.decode('utf-8')).read_bytes())
    return {'head': git('rev-parse', 'HEAD').decode('ascii').strip(),
            'tracked_diff_sha256': hashlib.sha256(git('diff', 'HEAD', '--binary')).hexdigest(),
            'untracked_sha256': untracked.hexdigest(),
            'tree_sitter': importlib.metadata.version('tree-sitter'),
            'language_pack': importlib.metadata.version('tree-sitter-language-pack')}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--signal', choices=['imports', 'calls'], default='imports')
    parser.add_argument('--corpus', action='append', default=[], metavar='ID',
                        help='measure only this recall corpus id (repeatable); compared to its own baseline rows')
    parser.add_argument('--write-baseline', action='store_true',
                        help='store reviewed new measurements (only the corpora measured), never used in scheduled CI')
    args = parser.parse_args(argv)
    manifest = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    if args.baseline is None:
        args.baseline = BASELINE.with_name('calls_baseline.json') if args.signal == 'calls' else BASELINE
    entries, errors = _selected(manifest, args.corpus, args.signal)
    current: dict[str, Any] = {}
    notes: list[str] = []
    for entry in entries:
        key = corpus_key(entry)
        started = time.monotonic()
        try:
            measurement = measure_calls if args.signal == 'calls' else measure
            current[key] = measurement(entry, (args.corpus_root / key).resolve())
            print(f'{key}: recall={current[key]["recall"]:.4%} precision={current[key]["precision"]:.4%} '
                  f'({current[key]["hit_edges"]}/{current[key]["oracle_edges"]} edges, '
                  f'{time.monotonic() - started:.0f}s)', flush=True)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError, SyntaxError) as exc:
            errors.append(f'{key}: {type(exc).__name__}: {exc}')
    if not current:
        errors.append('No corpus measurements completed')
    try:
        baseline = _read_baseline(args.baseline) if args.baseline.exists() or not args.write_baseline else {}
    except (OSError, ValueError) as exc:
        baseline = None
        errors.append(f'Baseline unavailable: {type(exc).__name__}: {exc}')
    if not errors and args.write_baseline:
        args.baseline.write_text(json.dumps({**baseline, **current}, indent=2) + '\n', encoding='utf-8')
    elif not errors and baseline is not None:
        if args.corpus:  # a partial run compares only the corpora it measured
            baseline = {k: v for k, v in baseline.items() if k in current}
        try:
            errors.extend(regressions(current, baseline, notes))
        except (KeyError, TypeError) as exc:
            errors.append(f'Baseline malformed: {type(exc).__name__}: {exc}')
    # The import signal scores one rule and names the combinations it declines (calls scores depth-1 callers).
    combinations = {'scored': SCORED_RULE, 'declined': list(DECLINED)} if args.signal == 'imports' else {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'measured_at': datetime.now(timezone.utc).isoformat(),
                                     'reveal_version': __version__, 'python': sys.version,
                                     'signal': args.signal, 'implementation': implementation_identity(),
                                     **combinations, 'measurements': current, 'failures': errors, 'notes': notes},
                                    indent=2) + '\n', encoding='utf-8')
    for note in notes:
        print(f'note: {note}', flush=True)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
