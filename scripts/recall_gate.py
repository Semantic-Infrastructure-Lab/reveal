#!/usr/bin/env python3
"""Pinned-corpus recall gate: independent import oracles vs depends:// on pinned corpora.

Each manifest entry with a ``recall:`` block names an oracle from scripts/recall_oracles.py
(a real compiler, the language's own parser, or a from-scratch resolution rule; never
Reveal's extractor or resolver). The gate checks the corpus is at its pinned commit, builds
the oracle over the configured importer population, builds Reveal's dependency graph over
the same scan root, and compares fan-in edges for every oracle target. Recall or precision
below the committed baseline, a changed population, an oracle or Reveal side that measured
nothing, or a missing corpus all fail; nothing is reported as a clean zero.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from recall_oracles import ORACLES, Scope, tracked_files
from reveal.adapters.depends import DependsAdapter, scan_extensions_for
from reveal import __version__

MANIFEST = Path(__file__).resolve().parent.parent / 'tests/corpus/manifest.yaml'
BASELINE = MANIFEST.with_name('recall_baseline.json')
# Fields whose change means the measured population moved: review the baseline, never auto-accept.
POPULATION_FIELDS = ('oracle', 'sha', 'targets', 'oracle_edges', 'coverage')


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
    adapter = DependsAdapter(resource=str(scan))
    # The parse corpus depends:// itself scans for a file target of this language.
    adapter._build_graph(scan, scan_extensions=scan_extensions_for(root / next(iter(edges))))
    if adapter._scan_capped:
        raise RuntimeError('Reveal scan was capped; measurement unavailable')
    population = set(importers)
    hit = expected = extra = 0
    differences = []
    for target, truth_list in edges.items():
        truth = set(truth_list)
        found = {p.relative_to(root).as_posix() for p in adapter._graph.reverse_deps.get(root / target, set())
                 if p in population}
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
            'coverage': coverage, 'partial_files': len(adapter._files_failed),
            'differences': differences}


def regressions(current: dict, baseline: dict) -> list[str]:
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
        for field in ('recall', 'precision'):
            if measured[field] + 1e-12 < reference[field]:
                failures.append(f'{key}: {field} dropped {reference[field]:.6%} -> {measured[field]:.6%}')
    return failures


def _selected(manifest: dict, wanted: list[str]) -> tuple[list[dict], list[str]]:
    entries = [e for e in manifest['corpora'] if 'recall' in e]
    if not wanted:
        return entries, []
    keys = {corpus_key(e) for e in entries}
    return [e for e in entries if corpus_key(e) in wanted], [f'{w}: no recall entry with that id'
                                                             for w in wanted if w not in keys]


def _read_baseline(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--corpus', action='append', default=[], metavar='ID',
                        help='measure only this recall corpus id (repeatable); compared to its own baseline rows')
    parser.add_argument('--write-baseline', action='store_true',
                        help='store reviewed new measurements (only the corpora measured), never used in scheduled CI')
    args = parser.parse_args(argv)
    manifest = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    entries, errors = _selected(manifest, args.corpus)
    current: dict[str, Any] = {}
    for entry in entries:
        key = corpus_key(entry)
        started = time.monotonic()
        try:
            current[key] = measure(entry, (args.corpus_root / key).resolve())
            print(f'{key}: recall={current[key]["recall"]:.4%} precision={current[key]["precision"]:.4%} '
                  f'({current[key]["hit_edges"]}/{current[key]["oracle_edges"]} edges, '
                  f'{time.monotonic() - started:.0f}s)', flush=True)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
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
            errors.extend(regressions(current, baseline))
        except (KeyError, TypeError) as exc:
            errors.append(f'Baseline malformed: {type(exc).__name__}: {exc}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'measured_at': datetime.now(timezone.utc).isoformat(),
                                     'reveal_version': __version__, 'python': sys.version,
                                     'measurements': current, 'failures': errors}, indent=2) + '\n', encoding='utf-8')
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
