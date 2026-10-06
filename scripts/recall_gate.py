#!/usr/bin/env python3
"""Pinned-corpus recall gate. First slice: independent GCC C include oracle.

Each literal quoted include is resolved in an isolated GCC translation unit;
Reveal's extractor/resolver never builds the oracle. Only configured importer
roots and in-corpus targets are measured. Unresolved directives are disclosed.
The compiler probe is qualified on POSIX hosts; Windows is not yet supported.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from reveal.adapters.depends import DependsAdapter
from reveal import __version__

MANIFEST = Path(__file__).resolve().parent.parent / 'tests/corpus/manifest.yaml'
BASELINE = MANIFEST.with_name('recall_baseline.json')
INCLUDES = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)
DEPTH_ONE = re.compile(r'^\. (.+)$', re.MULTILINE)
# One-line probes take milliseconds; a cold macOS runner (clang shim, first-run caches) stalled past 15 s
# once (BACK-1678). Generous, but a probe that still hangs is a measurement failure, never an empty row.
ORACLE_PROBE_TIMEOUT = 60


def tracked_importers(root: Path, directories: list[str]) -> list[Path]:
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                            check=True, capture_output=True, timeout=30)
    files = [Path(p.decode('utf-8')) for p in result.stdout.split(b'\0') if p]
    return [root / p for p in files if p.suffix in {'.c', '.h'} and
            any(p.is_relative_to(Path(d)) for d in directories)]


def resolve_c_include(root: Path, importer: Path, target: str, include_dirs: list[str], stub: Path) -> str | None:
    stub.write_text(f'#include "{target}"\n', encoding='utf-8')
    try:
        result = subprocess.run(['gcc', '-H', '-fsyntax-only', '-xc', f'-iquote{importer.parent}',
                                 *[f'-I{root / d}' for d in include_dirs], str(stub)],
                                cwd=root, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=ORACLE_PROBE_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'GCC oracle probe timed out after {ORACLE_PROBE_TIMEOUT}s resolving '
                           f'"{target}" from {importer}; measurement unavailable') from exc
    # Compilation can fail after opening the direct header (generated config,
    # platform macros). GCC's depth-one opened path is still authoritative.
    for opened in DEPTH_ONE.findall(result.stderr):
        path = (root / opened.strip()).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path.relative_to(root).as_posix()
    return None


def build_c_oracle(root: Path, config: dict) -> tuple[dict[str, list[str]], dict]:
    if sys.platform == 'win32':
        raise RuntimeError('GCC oracle prerequisite unavailable: Windows probe not qualified')
    if not shutil.which('gcc'):
        raise RuntimeError('GCC prerequisite unavailable')
    files = tracked_importers(root, config['importer_dirs'])
    edges: dict[str, set[str]] = defaultdict(set)
    resolved: dict[tuple[Path, str], str | None] = {}
    directives = unresolved = 0
    with tempfile.TemporaryDirectory(prefix='reveal-c-oracle-') as tmp:
        stub = Path(tmp) / 'include.c'
        for importer in files:
            source = importer.read_text(encoding='utf-8', errors='replace')
            for target in INCLUDES.findall(source):
                directives += 1
                key = (importer.parent, target)
                if key not in resolved:
                    resolved[key] = resolve_c_include(root, importer, target, config['include_dirs'], stub)
                path = resolved[key]
                if path is None:
                    unresolved += 1
                elif root / path != importer:
                    edges[path].add(importer.relative_to(root).as_posix())
    return {t: sorted(v) for t, v in sorted(edges.items())}, {
        'files': len(files), 'directives': directives, 'unresolved_directives': unresolved,
        'gcc_probes': len(resolved),
    }


def measure(entry: dict, root: Path) -> dict[str, Any]:
    head = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True,
                          capture_output=True, text=True, encoding='utf-8', timeout=30).stdout.strip()
    if not entry.get('sha') or head != entry['sha']:
        raise RuntimeError(f'Corpus pin mismatch: expected {entry.get("sha")}, got {head}')
    oracle, coverage = build_c_oracle(root, entry['recall'])
    if not oracle or not coverage['files'] or not coverage['directives']:
        raise RuntimeError('Oracle produced zero rows/files/directives; measurement unavailable')
    adapter = DependsAdapter(resource=str(root))
    adapter._build_graph(root, scan_extensions=frozenset({'.c', '.h'}))
    if adapter._scan_capped:
        raise RuntimeError('Reveal scan was capped; measurement unavailable')
    population = set(tracked_importers(root, entry['recall']['importer_dirs']))
    hit = expected = extra = 0
    differences = []
    for target, importers in oracle.items():
        truth = set(importers)
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
    return {'sha': head, 'targets': len(oracle), 'oracle_edges': expected, 'hit_edges': hit,
            'extra_edges': extra, 'recall': hit / expected, 'precision': hit / (hit + extra),
            'coverage': coverage, 'partial_files': len(adapter._files_failed),
            'differences': differences}


def regressions(current: dict, baseline: dict) -> list[str]:
    failures = []
    if not baseline:
        return ['Baseline is empty; measurement unavailable']
    for key in current.keys() - baseline.keys():
        failures.append(f'{key}: baseline missing; review required')
    for key, reference in baseline.items():
        measured = current.get(key)
        if not measured:
            failures.append(f'{key}: measurement missing')
            continue
        for field in ('sha', 'targets', 'oracle_edges', 'coverage'):
            if measured[field] != reference[field]:
                failures.append(f'{key}: oracle population/pin changed ({field}); baseline review required')
        for field in ('recall', 'precision'):
            if measured[field] + 1e-12 < reference[field]:
                failures.append(f'{key}: {field} dropped {reference[field]:.6%} -> {measured[field]:.6%}')
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--write-baseline', action='store_true', help='reviewed new measurements, never used in scheduled CI')
    args = parser.parse_args(argv)
    manifest = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    current, errors = {}, []
    for entry in manifest['corpora']:
        if 'recall' not in entry:
            continue
        key = entry.get('id', entry['language'])
        try:
            current[key] = measure(entry, (args.corpus_root / key).resolve())
            print(f'{key}: recall={current[key]["recall"]:.4%} precision={current[key]["precision"]:.4%}', flush=True)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            errors.append(f'{key}: {type(exc).__name__}: {exc}')
    if not current:
        errors.append('No corpus measurements completed')
    if not errors and args.write_baseline:
        args.baseline.write_text(json.dumps(current, indent=2) + '\n', encoding='utf-8')
    elif not errors:
        try:
            errors.extend(regressions(current, json.loads(args.baseline.read_text(encoding='utf-8'))))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'Baseline unavailable: {type(exc).__name__}: {exc}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'measured_at': datetime.now(timezone.utc).isoformat(),
                                     'reveal_version': __version__, 'python': sys.version,
                                     'measurements': current, 'failures': errors}, indent=2) + '\n', encoding='utf-8')
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
