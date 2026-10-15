#!/usr/bin/env python3
"""Bounded pinned mixed-framework validation using independent compiler/Python AST answers.

No corpus code is executed. The population is tests/corpus/framework_matrix.yaml;
actual results come from Reveal's existing AST, contracts and configuration owners.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fetch_corpus import MANIFEST, snapshot_status
from reveal.adapters.ast.analysis import analyze_file
from reveal.adapters.calls.references import jsx_component_references
from reveal.adapters.contracts import ContractsAdapter
from reveal.registry import get_analyzer

MATRIX = MANIFEST.with_name('framework_matrix.yaml')


def _compiler_answer(path: Path, toolchain: dict, mode: str) -> dict:
    command = Path(__file__).with_name('ts_import_oracle.cjs')
    result = subprocess.run(['node', str(command)], capture_output=True, text=True, encoding='utf-8',
                            input=json.dumps({'importers': [str(path)], 'config': toolchain, 'mode': mode}), timeout=60)
    if result.returncode:
        raise RuntimeError(f'Compiler oracle unavailable: {result.stderr.strip()}')
    return json.loads(result.stdout)


def check_file(path: Path, checks: list[str], toolchain: dict) -> dict:
    """Compare exact named/line results; a failed/zero prerequisite cannot be clean."""
    if not path.is_file():
        raise RuntimeError(f'Missing selected source: {path}')
    if not checks:
        raise RuntimeError('No framework checks selected')
    outcomes = {}
    for kind in checks:
        if kind in ('jsx', 'jsx-owner', 'interfaces'):
            answer = _compiler_answer(path, toolchain, 'jsx' if kind == 'jsx-owner' else kind)
            if kind == 'jsx':
                expected = Counter((r['line'], r['callee']) for r in answer['references'])
                structure = analyze_file(str(path))
                if structure is None:
                    raise RuntimeError('Reveal could not analyze selected JSX source')
                actual = Counter((r['line'], r['callee']) for r in structure.get('jsx_references', []))
            elif kind == 'jsx-owner':
                expected = Counter((r['line'], r['callee'], r['owner']) for r in answer['references'])
                structure = analyze_file(str(path))
                analyzer_class = get_analyzer(str(path))
                if structure is None or analyzer_class is None:
                    raise RuntimeError('Reveal could not analyze selected JSX owner source')
                analyzer = analyzer_class(str(path))
                analyzer.get_structure()
                actual = Counter((r['line'], r['callee'], r['owner'])
                                 for r in jsx_component_references(analyzer, structure['elements']))
            else:
                expected = Counter((r['line'], r['name']) for r in answer['protocols'])
                result = ContractsAdapter(str(path)).get_structure()
                if result.get('error') or result.get('meta', {}).get('errors'):
                    raise RuntimeError('Reveal contracts analysis failed')
                actual = Counter((r['line'], r['name']) for r in result['protocols'])
            outcomes[kind] = {'expected': sum(expected.values()), 'actual': sum(actual.values()),
                              'missing': list((expected - actual).elements()),
                              'extra': list((actual - expected).elements())}
        elif kind == 'python-abcs':
            tree = ast.parse(path.read_text(encoding='utf-8'))
            expected = Counter((n.lineno, n.name) for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
                               and any(isinstance(b, ast.Name) and b.id == 'ABC' for b in n.bases))
            result = ContractsAdapter(str(path)).get_structure()
            if result.get('error') or result.get('meta', {}).get('errors'):
                raise RuntimeError('Reveal ABC analysis failed')
            actual = Counter((r['line'], r['name']) for r in result['abcs'])
            outcomes[kind] = {'expected': sum(expected.values()), 'actual': sum(actual.values()),
                              'missing': list((expected - actual).elements()), 'extra': list((actual - expected).elements())}
        elif kind == 'json-config':
            expected = json.loads(path.read_text(encoding='utf-8'))
            analyzer_class = get_analyzer(str(path))
            if analyzer_class is None:
                raise RuntimeError('No configuration analyzer')
            structure = analyzer_class(str(path)).get_structure()
            if not structure or structure.get('_has_errors') or not expected:
                raise RuntimeError('Configuration source unavailable or empty')
            expected_keys = Counter(list(expected))
            actual_keys = Counter(row['name'] for row in structure['keys'])
            outcomes[kind] = {'expected': len(expected_keys), 'actual': sum(actual_keys.values()),
                              'missing': list((expected_keys - actual_keys).elements()),
                              'extra': list((actual_keys - expected_keys).elements())}
        else:
            raise ValueError(f'Unknown matrix check {kind}')
    if any(not row['expected'] or row['missing'] or row['extra'] for row in outcomes.values()):
        raise RuntimeError(f'Matrix mismatch or zero population: {outcomes}')
    return outcomes


def source_root(case: dict, manifest: dict, cache: Path) -> tuple[Path, str]:
    if 'corpus' in case:
        entry = next(e for e in manifest['corpora'] if e.get('id', e['language']) == case['corpus'])
        root, sha = cache / case['corpus'], entry['sha']
        head = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, encoding='utf-8', timeout=30, check=True).stdout.strip()
        if head != sha:
            raise RuntimeError('Selected corpus pin mismatch')
    else:
        entry = next(e for e in manifest['snapshots'] if e['id'] == case['snapshot'])
        root, status = snapshot_status(entry, manifest['snapshot_roots'], MANIFEST.parents[2])
        if status != 'ok' or not entry['sha']:
            raise RuntimeError(f'Selected snapshot pin unavailable: {status}')
        sha = entry['sha']
    return root.resolve(), sha


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    matrix = yaml.safe_load(MATRIX.read_text(encoding='utf-8'))
    records, failures = [], []
    for case in matrix['cases']:
        try:
            root, sha = source_root(case, manifest, args.corpus_root)
            path = (root / case['file']).resolve()
            if not path.is_relative_to(root):
                raise RuntimeError('Selected source escapes corpus root')
            outcomes = check_file(path, case['checks'], matrix['toolchain'])
            records.append({'id': case['id'], 'sha': sha, 'file': case['file'], 'outcomes': outcomes})
            print(case['id'], outcomes, flush=True)
        except (OSError, RuntimeError, ValueError, SyntaxError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
            failures.append(f"{case['id']}: {exc}")
    if not records:
        failures.append('No framework sources measured')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'measured_at': datetime.now(timezone.utc).isoformat(),
                                      'toolchain': matrix['toolchain'], 'records': records,
                                      'scope_exclusions': matrix['exclusions'], 'failures': failures}, indent=2) + '\n', encoding='utf-8')
    for failure in failures:
        print(failure)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
