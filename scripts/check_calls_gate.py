#!/usr/bin/env python3
"""Require recorded calls measurements for function/caller changes (BACK-2204).

The external measurement runner owns oracle comparisons. This helper selects the
required rows from its configured baseline and checks the recorded run's identity.
Use --describe to obtain the request an external recorder must satisfy; --rows
is available only with --describe for qualifying a bounded recorder run.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys


def git(repo, *args):
    return subprocess.run(
        ['git', '-C', str(repo), *args], check=True, capture_output=True,
        text=True, encoding='utf-8', timeout=30,
    ).stdout.strip()


def changed_paths(repo, base):
    """Disable rename detection so old and new paths both participate in selection."""
    tracked = git(repo, 'diff', '--name-only', '--no-renames', '-z', base)
    new = git(repo, 'ls-files', '--others', '--exclude-standard', '-z')
    return sorted(set(filter(None, tracked.split('\0') + new.split('\0'))))


def path_languages(path):
    """None requires every baseline row; an empty set is unrelated to calls."""
    shared = {
        'reveal/base.py', 'reveal/treesitter.py', 'reveal/structure.py',
        'reveal/conventions.py', 'reveal/registry.py',
        'reveal/utils/parallel.py', 'reveal/utils/pyparse.py',
    }
    if path in shared or path.startswith('reveal/adapters/calls/'):
        return None
    if path in {'reveal/adapters/ast/nav_calls.py', 'reveal/adapters/ast/call_graph.py'}:
        return None
    if path.startswith('reveal/analyzers/imports/'):
        return set()
    if not path.endswith('.py'):
        return set()
    if path.startswith(('reveal/analyzers/', 'reveal/core/callees/')):
        name = Path(path).stem
        if name in {'javascript', 'typescript', 'js'} or name.startswith('_js'):
            return {'javascript', 'typescript'}
        if name.startswith('_python'):
            return {'python'}
        if name in {'c', 'cpp'}:
            return {'c', 'cpp'}
        return {name} if not name.startswith('_') else None
    return None if path.startswith('reveal/core/') else set()


def required_rows(paths, baseline):
    wanted = set()
    available = {key.split('/')[0] for key in baseline}
    for path in paths:
        languages = path_languages(path)
        if languages is None:
            return sorted(baseline)
        expanded = {pair for pair in available for lang in languages
                    if pair == lang or (lang == 'javascript' and pair.startswith('js_'))}
        if languages and not expanded:
            return sorted(baseline)  # Unknown relevant analyzers must not silently bypass the gate.
        wanted.update(expanded)
    return sorted(key for key in baseline if key.split('/')[0] in wanted)


def toolchain(interpreter):
    code = (
        "import importlib.metadata,json,os,platform,sys; "
        "print(json.dumps({'executable':os.path.abspath(sys.executable),"
        "'python':platform.python_version(),'tree_sitter_language_pack':"
        "importlib.metadata.version('tree-sitter-language-pack')}))"
    )
    run = subprocess.run(
        [str(interpreter), '-c', code], check=True, capture_output=True,
        text=True, encoding='utf-8', timeout=30,
    )
    return json.loads(run.stdout)


def build_request(repo, baseline_path, interpreter, rows=None):
    """Describe the clean checkout and exact external rows required for this run."""
    repo = Path(git(repo, 'rev-parse', '--show-toplevel')).resolve()
    try:
        upstream = git(repo, 'rev-parse', '--symbolic-full-name', '@{upstream}')
    except subprocess.CalledProcessError:
        upstream = 'refs/remotes/origin/master'
    base = git(repo, 'merge-base', 'HEAD', upstream)
    paths = changed_paths(repo, base)
    request = {
        'schema_version': 1, 'checkout': str(repo),
        'head': git(repo, 'rev-parse', 'HEAD'),
        'tree': git(repo, 'rev-parse', 'HEAD^{tree}'),
        'base': base, 'changed_paths': paths, 'required_rows': [],
    }
    relevant = any(path_languages(path) != set() for path in paths)
    if not relevant and rows is None:
        return request
    if baseline_path is None:
        raise ValueError('calls gate requires REVEAL_CALLS_GATE_BASELINE or --baseline')
    raw = Path(baseline_path).read_bytes()
    baseline = json.loads(raw)
    if not isinstance(baseline, dict) or not baseline or any(
            not isinstance(k, str) or '/' not in k for k in baseline):
        raise ValueError('calls gate baseline must contain named language/mode rows')
    selected = required_rows(paths, baseline) if rows is None else sorted(set(rows))
    if not selected or set(selected) - set(baseline):
        raise ValueError('calls gate requested rows are empty or absent from the baseline')
    if git(repo, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('calls gate evidence requires a clean analyzed checkout; commit changes first')
    request.update(required_rows=selected, baseline_sha256=hashlib.sha256(raw).hexdigest(),
                   toolchain=toolchain(interpreter))
    return request


def validate_evidence(request, evidence):
    """Return None for matching green evidence; otherwise raise ValueError."""
    if not isinstance(evidence, dict):
        raise ValueError('calls gate evidence must be a JSON object')
    identity = ('schema_version', 'checkout', 'head', 'tree', 'base', 'changed_paths', 'required_rows',
                'baseline_sha256', 'toolchain')
    for key in identity:
        if key not in request or evidence.get(key) != request[key]:
            raise ValueError(f'calls gate evidence has stale or mismatched {key}')
    measured_at = evidence.get('measured_at')
    if not isinstance(measured_at, str):
        raise ValueError('calls gate evidence lacks measured_at')
    recorded = datetime.fromisoformat(measured_at)
    if recorded.utcoffset() is None:
        raise ValueError('calls gate measured_at must include its timezone')
    if recorded > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('calls gate measured_at is in the future')
    if evidence.get('failures') != []:
        raise ValueError('calls gate evidence is failed or lacks an explicit empty failures list')
    measurements = evidence.get('measurements')
    if not isinstance(measurements, dict):
        raise ValueError('calls gate evidence lacks measurements')
    for key in request['required_rows']:
        row = measurements.get(key)
        if not isinstance(row, dict) or row.get('reveal_sha') != request['head']:
            raise ValueError(f'calls gate row {key} is missing or measured another revision')
        validate_row(key, row)


def validate_row(key, row):
    positive = (row.get('oracle_edges'), row.get('sample_size'))
    if any(type(value) is not int or value <= 0 for value in positive):
        raise ValueError(f'calls gate row {key} measured nothing')
    counts = (row.get('found_edges'), row.get('false_positive_edges'))
    if any(type(value) is not int or value < 0 for value in counts):
        raise ValueError(f'calls gate row {key} has invalid edge counts')
    recall = row.get('recall')
    if type(recall) not in (int, float) or not math.isfinite(recall) or not 0 <= recall <= 1:
        raise ValueError(f'calls gate row {key} has invalid recall')
    targets = row.get('targets')
    if not isinstance(targets, dict) or not targets:
        raise ValueError(f'calls gate row {key} lacks target measurements')
    for name, values in targets.items():
        if not isinstance(name, str) or not name or not isinstance(values, list) or len(values) != 2:
            raise ValueError(f'calls gate row {key} has malformed target measurements')
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError(f'calls gate row {key} has invalid target counts')


def audit(path, repo, decision, detail):
    """Keep overrides and refusals visible after the terminal session ends."""
    record = {'timestamp': datetime.now(timezone.utc).isoformat(), 'checkout': str(repo),
              'decision': decision, 'detail': detail}
    try:
        record.update(head=git(repo, 'rev-parse', 'HEAD'), tree=git(repo, 'rev-parse', 'HEAD^{tree}'))
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        record['head'] = None  # A refusal outside a readable Git checkout is still logged.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, sort_keys=True) + '\n')


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--baseline', type=Path, default=os.environ.get('REVEAL_CALLS_GATE_BASELINE'))
    parser.add_argument('--evidence', type=Path, default=os.environ.get('REVEAL_CALLS_GATE_EVIDENCE'))
    parser.add_argument('--interpreter', type=Path, required=True)
    parser.add_argument('--describe', action='store_true')
    parser.add_argument('--rows', nargs='+')
    parser.add_argument('--skip-reason')
    parser.add_argument('--log', type=Path, default=Path.home() / '.cache/reveal-ci/logs/calls-gate.jsonl')
    args = parser.parse_args(argv)
    if args.rows is not None and not args.describe:
        parser.error('--rows is request-only and requires --describe')
    if args.skip_reason is not None and (not args.skip_reason.strip() or args.describe):
        parser.error('--skip-reason requires a nonempty reason and cannot accompany --describe')
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.skip_reason is not None:
            detail = f'calls gate SKIPPED explicitly: {args.skip_reason}'
            audit(args.log, args.repo.resolve(), 'skip', detail)
            print(detail, file=sys.stderr)
            return 0
        request = build_request(args.repo, args.baseline, args.interpreter, args.rows)
        if args.describe:
            print(json.dumps(request, indent=2, sort_keys=True))
            return 0
        if not request['required_rows']:
            detail = 'calls gate: no function/caller paths changed in the unpushed range'
        else:
            if args.evidence is None:
                raise ValueError('calls gate requires recorded green evidence (--calls-evidence PATH)')
            validate_evidence(request, json.loads(args.evidence.read_text(encoding='utf-8')))
            detail = f"calls gate: verified {len(request['required_rows'])} rows at {request['head'][:12]}"
        audit(args.log, args.repo.resolve(), 'pass', detail)
        print(detail)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = f'calls gate FAILED: {exc}'
        audit(args.log, args.repo.resolve(), 'fail', detail)
        print(detail, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
