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

from recall_oracles import ORACLES, Scope, tracked_files, build_python_calls_oracle
from reveal.adapters.depends import DependsAdapter
from reveal.main import main as reveal_main
from reveal.utils.request_cache import reset_request_caches
from reveal import __version__

MANIFEST = Path(__file__).resolve().parent.parent / 'tests/corpus/manifest.yaml'
BASELINE = MANIFEST.with_name('recall_baseline.json')
# Fields whose change means the measured population moved: review the baseline, never auto-accept.
POPULATION_FIELDS = ('oracle', 'sha', 'targets', 'oracle_edges', 'coverage')


_PARTIAL_PARSE = re.compile(r'(\d+) file\(s\) parsed with errors')


@contextlib.contextmanager
def _scan_cap(cap: int):
    """The one knob without a per-request spelling: depends:// reads the class default."""
    before = DependsAdapter._SCAN_FILE_CAP
    DependsAdapter._SCAN_FILE_CAP = cap
    try:
        yield
    finally:
        DependsAdapter._SCAN_FILE_CAP = before


def _cli_json(uri: str, label: str) -> dict[str, Any]:
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
    if code or result.get('error'):
        raise RuntimeError(f'{scheme}:// failed for {label} (exit {code}): {result.get("error") or err.getvalue()[:200]}')
    return result


def _depends_request(target: Path, scan: Path) -> dict[str, Any]:
    """One ``depends://`` request; a capped scan raises like any other failed answer."""
    result = _cli_json(f'depends://{target.as_posix()}?root={urllib.parse.quote(scan.as_posix(), safe="/:")}',
                       target.name)
    if result.get('metadata', {}).get('scan_capped'):
        raise RuntimeError('Reveal scan was capped; measurement unavailable')
    return result


def _partial_files(result: dict[str, Any]) -> int:
    """The partial-parse count, which the public JSON carries only in the warning text."""
    warning = result.get('warning') or ''
    found = _PARTIAL_PARSE.search(warning)
    if 'parsed with errors' in warning and not found:
        raise RuntimeError(f'Unrecognized partial-parse disclosure: {warning[:200]}')
    return int(found.group(1)) if found else 0


def rendered_dependents(scan: Path, target: Path) -> dict[str, Any]:
    """Importers of one file as ``depends://<file>`` prints them: the package view Go needs, where an
    import names a directory. It builds the whole graph per request, so use it only where the
    directory form below cannot answer."""
    result = _depends_request(target, scan)
    dependents = result['dependents']
    if len(dependents) != result['count']:
        raise RuntimeError(f'depends:// answer truncated for {target.name}: {len(dependents)} of {result["count"]} shown')
    return {'importers': {Path(os.path.normpath(scan / dep['file'])) for dep in dependents},
            'partial_files': _partial_files(result)}


def rendered_reverse_graph(scan: Path) -> dict[str, Any]:
    """Every module's importers from ONE ``depends://<scan dir>`` request (the dependency summary).

    ``depends://<file>`` rebuilds the full import graph per request (4837 files, 10-28 s each on
    the Java corpus), so a per-target gate would take hours; the directory summary lists
    every module with its sorted importers in a single answer.
    """
    result = _depends_request(scan, scan)
    modules = result['modules']
    if len(modules) != result['total_modules']:
        raise RuntimeError(f'depends:// summary truncated: {len(modules)} of {result["total_modules"]} modules shown')
    return {'by_target': {Path(os.path.normpath(scan / m['module'])): {Path(os.path.normpath(scan / d)) for d in m['dependents']}
                          for m in modules},
            'partial_files': _partial_files(result)}


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
    # The parse corpus depends:// itself scans for a file target of this language.
    cap = config.get('scan_file_cap', DependsAdapter._SCAN_FILE_CAP)
    if not isinstance(cap, int) or cap <= 0:
        raise RuntimeError('scan_file_cap must be a positive integer')
    excluded_suffixes = tuple(config.get('exclude_importer_suffixes', []))
    population = {p for p in importers if not excluded_suffixes or not p.name.endswith(excluded_suffixes)}
    hit = expected = extra = partial = 0
    differences = []
    with _scan_cap(cap):
        reset_request_caches()
        # Go imports name packages, so its per-file answer is the package view of depends://<file>.
        graph = None if name == 'go-toolchain' else rendered_reverse_graph(scan)
        for target, truth_list in edges.items():
            if graph is None:
                view = rendered_dependents(scan, root / target)
                importers, partial = view['importers'], view['partial_files']
            else:
                importers, partial = graph['by_target'].get(root / target, set()), graph['partial_files']
            truth = set(truth_list)
            found = {p.relative_to(root).as_posix() for p in importers if p in population}
            matched, missed, surplus = truth & found, truth - found, found - truth
            hit += len(matched)
            expected += len(truth)
            extra += len(surplus)
            if missed or surplus:
                differences.append({'target': target, 'missed': sorted(missed), 'extra': sorted(surplus)})
    if not hit:
        raise RuntimeError('Reveal found zero oracle edges; positive control failed')
    return {'oracle': name, 'sha': head, 'targets': len(edges), 'oracle_edges': expected, 'hit_edges': hit,
            'extra_edges': extra, 'recall': hit / expected, 'precision': hit / (hit + extra),
            'coverage': coverage, 'partial_files': partial,
            'differences': differences}


def measure_calls(entry: dict, root: Path) -> dict[str, Any]:
    """Measure the existing public callers projection against independent Python AST."""
    from reveal.adapters.calls.index import find_callers
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
    for target, truth_list in edges.items():
        answer = find_callers(str(scan), target)
        truth = set(truth_list)
        found = {f"{Path(row['file']).relative_to(root).as_posix()}::{row['caller']}"
                 for level in answer['levels'] for row in level['callers']
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
    return failures


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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'measured_at': datetime.now(timezone.utc).isoformat(),
                                     'reveal_version': __version__, 'python': sys.version,
                                     'signal': args.signal, 'implementation': implementation_identity(),
                                     'measurements': current, 'failures': errors, 'notes': notes}, indent=2) + '\n', encoding='utf-8')
    for note in notes:
        print(f'note: {note}', flush=True)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
