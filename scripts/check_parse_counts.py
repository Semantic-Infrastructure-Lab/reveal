#!/usr/bin/env python3
"""Qualify cold serial owned-parser counts; measure before accepting ceilings.

Only the two opt-in parser seams are observed. Third-party/startup ast.parse,
annotation/V-series bypasses and native retries inside ts_parse are uninstrumented,
not zero. Attributed snippet/validation/external events remain in the vector.
This establishes neither parallel accounting nor cross-command reuse.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'scripts' / 'parse_counts_manifest.json'
BASELINE = ROOT / 'scripts' / 'parse_counts_baseline.json'
EVENTS = ('request', 'attempt', 'artifact', 'failure', 'outcome')
COVERAGE = (
    'Measured: owned parser-seam requests, wrapper/Python attempts, artifacts and outcomes; '
    'fullsource/snippet/validation and target/external/unattributed are distinct. '
    'Uninstrumented: third-party/generated/startup direct ast.parse, direct annotation '
    'and V-series bypasses, native retries inside ts_parse. No parallel or cross-command claim. '
    'Runtime/version metadata must repeat across five current runs; historical versions are provenance, '
    'not ceilings. New parser/domain/content/count identities still fail the accepted ceilings.'
)

# SystemExit is caught INSIDE capture so validation runs even on a CLI findings exit.
_BOOTSTRAP = '''
import sys, json, platform
from dataclasses import asdict
from pathlib import Path
from reveal.utils.parse_audit import capture_parses
root, destination, targets, arguments = sys.argv[1:]
signal = None
with capture_parses(root, targets=json.loads(targets)) as capture:
    capture.metadata['runtime'] = {'platform': sys.platform, 'implementation': platform.python_implementation()}
    from reveal.main import main
    sys.argv = ['reveal'] + json.loads(arguments)
    try:
        main()
    except SystemExit as error:
        signal = error
status = 0 if signal is None or signal.code is None else signal.code
if not isinstance(status, int):
    status = 1
Path(destination).write_text(json.dumps({
    'schema_version': 1, 'complete': True, 'exit_code': status,
    'metadata': capture.metadata, 'events': [asdict(e) for e in capture.events]
}), encoding='utf-8')
if signal is not None:
    raise signal
'''


def load_audit(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError(f'missing or invalid audit: {path}: {error}') from error
    if not isinstance(result, dict):
        raise ValueError('audit must be a JSON object')
    return result


def _validate_header(audit: dict, root_pid: int) -> None:
    if audit.get('schema_version') != 1 or audit.get('complete') is not True:
        raise ValueError('audit is not complete')
    metadata = audit.get('metadata', {})
    if metadata.get('pid') != root_pid or not metadata.get('parser_versions'):
        raise ValueError('audit root PID or parser metadata missing')
    versions = metadata['parser_versions']
    required = {'python.ast', 'tree-sitter', 'tree-sitter-language-pack'}
    if not required.issubset(versions) or not versions['python.ast']:
        raise ValueError('parser version metadata incomplete')
    runtime = metadata.get('runtime') or {}
    if not runtime.get('platform') or not runtime.get('implementation'):
        raise ValueError('child runtime metadata incomplete')
    if audit.get('exit_code') != 0:
        raise ValueError('audit reports command failure exit')


def _target_identity(event: dict, corpus: Path, targets: dict) -> tuple[str | None, str | None]:
    filename = event['filename']
    relative = None
    if filename is not None:
        path = Path(filename)
        if path.is_relative_to(corpus):
            relative = path.relative_to(corpus).as_posix()
    if event['scope'] != 'target':
        if relative in targets:
            raise ValueError('target was mislabeled as external')
        return relative, None
    if relative not in targets:
        raise ValueError('unknown target attribution')
    expected = targets[relative]
    if event['parser'] not in expected['parsers']:
        raise ValueError(f'unexpected target parser: {relative}: {event["parser"]}')
    variant = None
    if event['domain'] == 'fullsource':
        variants = expected.get('variants', {'canonical': expected})
        variant = next((label for label, identity in variants.items()
                        if event['source_hash'] == identity['sha256']
                        and event['source_length'] == identity['bytes']), None)
        if variant is None:
            raise ValueError(f'target content identity differs from declared variants: {relative}')
    return relative, variant


def _count_key(event: dict, relative: str | None, variant: str | None, targets: dict) -> str:
    # External paths are retained, never silently treated as target or excluded.
    filename = relative if event['scope'] == 'target' else event['filename']
    key = {field: event[field] for field in (
        'event', 'parser', 'domain', 'scope', 'source_hash', 'source_length',
        'parsed_hash', 'phase', 'outcome', 'error')}
    key['filename'] = filename
    key['source_variant'] = variant
    key['original_source_hash'] = targets[relative]['sha256'] if event['scope'] == 'target' else None
    return json.dumps(key, sort_keys=True, separators=(',', ':'))


def _validate_event_shape(event: dict) -> None:
    choices = {'event': EVENTS, 'domain': ('fullsource', 'snippet', 'validation'),
               'scope': ('target', 'external', 'unattributed')}
    for field, values in choices.items():
        if event[field] not in values:
            raise ValueError(f'unknown audit {field}: {event[field]}')


def audit_snapshot(audit: dict, root_pid: int, corpus: Path, targets: dict) -> dict:
    from reveal.utils.parse_audit import ParseCapture, ParseEvent
    _validate_header(audit, root_pid)
    corpus = corpus.resolve()
    rows = audit.get('events')
    if not isinstance(rows, list) or not rows:
        raise ValueError('audit contains no parser evidence')
    try:
        events = [ParseEvent(**row) for row in rows]
    except (TypeError, KeyError) as error:
        raise ValueError(f'invalid audit event: {error}') from error
    ParseCapture(corpus, events=events).validate()
    counts: Counter = Counter()
    totals = dict.fromkeys(EVENTS, 0)
    coverage = set()
    for event in rows:
        _validate_event_shape(event)
        if event['pid'] != root_pid:
            raise ValueError('non-root PID parser event; serial qualification failed')
        relative, variant = _target_identity(event, corpus, targets)
        if event['event'] == 'outcome' and event['outcome'] == 'failed':
            raise ValueError('failed parser outcome')
        if event['event'] == 'request' and event['scope'] == 'target' and event['domain'] == 'fullsource':
            coverage.add(relative)
        counts[_count_key(event, relative, variant, targets)] += 1
        totals[event['event']] += 1
    if coverage != set(targets):
        raise ValueError(f'target request coverage incomplete: {sorted(coverage)} != {sorted(targets)}')
    return {'parser_versions': audit['metadata']['parser_versions'],
            'runtime': audit['metadata']['runtime'], 'coverage': sorted(coverage),
            'totals': totals, 'counts': dict(sorted(counts.items()))}


def _require_values(actual: dict, expected: dict) -> None:
    for field, wanted in expected.items():
        if actual.get(field) != wanted:
            raise ValueError(f'command outcome {field}: {actual.get(field)!r} != {wanted!r}')


def _validate_analysis_state(node: Any, allowed_warnings: list[str]) -> None:
    """Inspect composed JSON metadata as well as the parent result envelope."""
    if isinstance(node, list):
        for child in node:
            _validate_analysis_state(child, allowed_warnings)
    elif isinstance(node, dict):
        if node.get('error') or node.get('errors'):
            raise ValueError(f'command reported errors: {node.get("error") or node["errors"]}')
        if node.get('applicable') is False:
            raise ValueError('command analysis was not applicable')
        if any(node.get(key) for key in ('analysis_failed', 'parse_degraded', 'check_rules_failed')):
            raise ValueError('command analysis was incomplete')
        for warning in node.get('warnings', []):
            if not isinstance(warning, dict) or warning.get('type') not in allowed_warnings:
                raise ValueError(f'command warning is not qualified: {warning}')
        for child in node.values():
            _validate_analysis_state(child, allowed_warnings)


def validate_command_output(status: int, stdout: str, spec: dict, target_count: int) -> dict:
    if status != spec['exit_code']:
        raise ValueError(f'command exit {status}, expected {spec["exit_code"]}')
    try:
        result = json.loads(stdout)
    except ValueError as error:
        raise ValueError('command did not produce valid JSON') from error
    if not isinstance(result, dict) or result.get('type') != spec['type']:
        raise ValueError('command JSON type differs from manifest')
    meta = result.get('meta') or {}
    _validate_analysis_state(result, spec.get('allowed_warning_types', []))
    if spec['type'] == 'check':
        disclosures = result.get('summary', {}).get('scan_disclosures', [])
        if disclosures != spec.get('allowed_scan_disclosures', []):
            raise ValueError(f'command scan_disclosures not qualified: {disclosures}')
    summary = _outcome_summary(result, target_count)
    return {**summary, 'warnings': meta.get('warnings', [])}


def _outcome_summary(result: dict, target_count: int) -> dict:
    kind = result['type']
    summary = result.get('summary', {})
    if kind == 'check':
        _require_values(summary, {'files_checked': target_count, 'total_issues': 0,
                                 'files_errored': 0, 'files_degraded': 0, 'exit_code': 0})
        return {key: summary.get(key) for key in ('files_checked', 'total_issues', 'files_errored',
                                                 'files_degraded', 'exit_code', 'scan_disclosures')}
    if kind == 'overview':
        summary = result.get('stats', {}).get('summary', {})
    if kind in ('overview', 'hotspots'):
        _require_values(summary, {'total_files': target_count, 'excluded': 0})
        return {'total_files': target_count, 'excluded': 0}
    _require_values(result.get('scope', {}), {'total_code_files': target_count})
    if result.get('unparsed_files') or result.get('recovered_files') or result.get('unsupported_language'):
        raise ValueError('surface coverage is incomplete or degraded')
    _require_values(result, {'total': target_count})
    return {'total_code_files': target_count, 'env_findings': result['total']}


def qualify_snapshots(snapshots: list[dict]) -> dict:
    if len(snapshots) != 5:
        raise ValueError('qualification requires exactly five fresh runs')
    if any(snapshot != snapshots[0] for snapshot in snapshots[1:]):
        raise ValueError('fresh-run counts/outcomes do not repeat exactly')
    return snapshots[0]


def compare_snapshots(baseline: dict, current: dict) -> list[str]:
    errors = [f'{key} changed' for key in ('coverage', 'command_outcome', 'stderr')
              if baseline.get(key) != current.get(key)]
    for key, count in current['counts'].items():
        ceiling = baseline['counts'].get(key, 0)
        if count > ceiling:
            errors.append(f'{key}: {ceiling} -> {count}')
    return errors


def _environment(config_home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.pop('PYTHONPYCACHEPREFIX', None)
    env.update(REVEAL_MAX_WORKERS='1', REVEAL_DISK_CACHE='0', PYTHONPATH=str(ROOT),
               PYTHONHASHSEED='0', PYTHONIOENCODING='utf-8', XDG_CONFIG_HOME=str(config_home))
    return env


def run_once(spec: dict, corpus: Path, targets: dict, run_directory: Path) -> dict:
    audit_path = run_directory / 'audit.json'
    config_home = run_directory / 'config'
    config_home.mkdir()
    arguments = [str(corpus) if arg == '{corpus}' else arg for arg in spec['args']]
    command = [sys.executable, '-c', _BOOTSTRAP, str(corpus), str(audit_path),
               json.dumps(list(targets)), json.dumps(arguments)]
    with subprocess.Popen(command, cwd=corpus, env=_environment(config_home),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8') as process:
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=10)
            raise ValueError('command timed out before audit completion')
        try:
            outcome = validate_command_output(process.returncode, stdout, spec, len(targets))
            snapshot = audit_snapshot(load_audit(audit_path), process.pid, corpus, targets)
        except ValueError as error:
            raise ValueError(f'{arguments}: {error}\nstdout:\n{stdout}\nstderr:\n{stderr}') from error
    snapshot['command_outcome'] = outcome
    snapshot['stderr'] = stderr.replace(str(corpus), '<corpus>')
    return snapshot


def _source_identity(source: str) -> dict:
    encoded = source.encode('utf-8', 'surrogatepass')
    return {'sha256': sha256(encoded).hexdigest(), 'bytes': len(encoded)}


def _verify_corpus(corpus: Path, targets: dict) -> None:
    actual = {path.relative_to(corpus).as_posix() for path in corpus.rglob('*') if path.is_file()}
    if actual != set(targets):
        raise ValueError('corpus file set differs from manifest')
    for name, expected in targets.items():
        text = (corpus / name).read_text(encoding='utf-8')
        canonical = _source_identity(text)
        _require_values(canonical, {key: expected[key] for key in ('sha256', 'bytes')})
        variants = {'canonical': canonical}
        if text.endswith('\n'):
            variants['analyzer-content'] = _source_identity(text[:-1])
        if expected.get('variants', variants) != variants:
            raise ValueError(f'declared source variants differ from corpus: {name}')


def measure(manifest: dict) -> dict:
    corpus_source = ROOT / manifest['corpus']
    targets = manifest['targets']
    _verify_corpus(corpus_source, targets)
    commands = {}
    with tempfile.TemporaryDirectory(prefix='reveal-parse-gate-') as temporary:
        directory = Path(temporary)
        for name, spec in manifest['commands'].items():
            snapshots = []
            for repeat in range(manifest['repeats']):
                run_directory = directory / f'{name}-{repeat}'
                run_directory.mkdir()
                corpus = run_directory / 'corpus'
                shutil.copytree(corpus_source, corpus)
                snapshots.append(run_once(spec, corpus, targets, run_directory))
            commands[name] = qualify_snapshots(snapshots)
    return {'schema_version': 1, 'qualification_platform': sys.platform,
            'coverage_policy': COVERAGE, 'manifest': manifest, 'commands': commands}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measure', action='store_true', help='write candidate evidence; never accept ceilings')
    parser.add_argument('--output', type=Path, help='candidate JSON destination (required with --measure)')
    args = parser.parse_args()
    if args.measure and args.output is None:
        parser.error('--measure requires --output; measured values need review before acceptance')
    try:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
        current = measure(manifest)
        if args.measure:
            args.output.write_text(json.dumps(current, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            print(f'Qualified five fresh serial runs per command; candidate: {args.output}')
            return 0
        baseline = load_audit(BASELINE)
        if baseline.get('manifest') != manifest or baseline.get('coverage_policy') != COVERAGE:
            raise ValueError('accepted manifest/coverage policy changed; requalification required')
        errors = [f'{name}: {error}' for name, snapshot in current['commands'].items()
                  for error in compare_snapshots(baseline['commands'][name], snapshot)]
        if errors:
            raise ValueError('\n'.join(errors))
        print('Cold serial owned-parser count ceilings satisfied (five fresh runs per command).')
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(f'parse-count qualification failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
