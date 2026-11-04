#!/usr/bin/env python3
"""Rule census: per-language rule fire rates over the pinned corpora, with oracle-free invariants.

Runs ``reveal check <corpus> --format json`` on each pinned corpus of tests/corpus/manifest.yaml that
is present under --corpus-root, at its pin and unmodified, and not larger than --max-source-mb of
tracked source (default 100 MB: the 17 corpora up to zig, none of the 11 larger ones). Needs no oracle
and no labels, so it runs in every language (REVEAL_PLAN rule 8) and says nothing about recall.

Counting rules (stated in the JSON too, plan rule 4):
  * a finding is one detection record (rule, file, line) in the check JSON;
  * the rate is findings per 100 files, where files = ``summary.files_checked`` of that run, every
    file the run scanned of any language, so a language-specific rule is diluted by the others;
  * an outlier is a corpus whose rate for a rule exceeds 5x the median rate of the corpora where the
    rule fired at least once, for rules with at least --min-hits findings in total. Outliers are
    reported, never failed: a high rate can be a true property of the code.

Two invariants hold with no ground truth, and any violation fails the run naming each finding:
  * self-line: no duplicate-style finding names its own line as the earlier occurrence. I005 writes
    "(first imported at line N)", D001 and D002 write "(line N)" (reveal/rules/imports/I005.py,
    duplicates/D001.py, D002.py). A message of such a rule that does not carry a pointer is itself a
    violation, so a reworded message cannot make the check pass by matching nothing.
  * I002 versus ``imports://<corpus>?circular`` (BACK-2156 option B, one finding per file per cycle
    group): the files with an I002 finding are exactly the load-order-language members of the cycle
    groups, once each, except members ``check`` records as skipped or errored (generated files, which
    no rule judges). Members in languages outside ``capabilities.LOAD_ORDER_CYCLE_LANGUAGES`` are not
    expected to carry a finding (the language gate). Relation: findings == judged members, per file.

Exit status: 0 clean; 1 an invariant violation; 2 a failed measurement (any ``check`` exit other than
0, 1 or 3, a timeout, unparsable or truncated output, a pin mismatch) or a usage error. A failed
corpus is a failure and contributes no rows; it is never read as zero findings.

Usage:
  PYTHONPATH=$PWD REVEAL_DISK_CACHE=0 python scripts/rule_census.py --output /scratch/census.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from fetch_corpus import _load_manifest
from recall_gate import corpus_key, implementation_identity
from rule_precision import source_identity
from reveal.capabilities import load_order_cycle_extension
from reveal.utils.path_utils import to_posix

DOCUMENTED_EXITS = (0, 1, 3)  # check: clean, findings, scan incomplete (AGENT_HELP, exit codes)
OUTLIER_FACTOR = 5
DEFAULT_MIN_HITS = 50
DEFAULT_MAX_SOURCE_MB = 100
DEFAULT_TIMEOUT = 900
UNJUDGED_STATUSES = ('skipped', 'error')  # records no rule ran on (generated, unreadable)

# Rules whose message points at another location, and the exact tail that carries that line.
POINTER_PATTERNS: dict[str, re.Pattern[str]] = {
    'I005': re.compile(r'\(first imported at line (\d+)\)$'),
    'D001': re.compile(r"identical to '.*' \(line (\d+)\)$", re.DOTALL),
    'D002': re.compile(r"similar to '.*' \(line (\d+)\)$", re.DOTALL),
}

COUNTING_RULES = {
    'finding': 'one detection record (rule, file, line) in the check JSON',
    'rate': 'findings per 100 files; files = summary.files_checked of that run (every language)',
    'outlier': f'rate above {OUTLIER_FACTOR}x the median rate over corpora where the rule fired at least once, '
               'for rules with at least min_hits findings in total; reported, never failed',
    'self_line': 'a duplicate-style finding whose pointer line equals its own line; a message without a pointer '
                 'also fails',
    'i002_circular': 'files with an I002 finding == load-order-language members of imports://?circular groups '
                     'that check judged, one finding each',
}


class MeasurementFailed(Exception):
    """A corpus could not be measured. Never read as zero findings."""


# ---------------------------------------------------------------- pure aggregation

def report_files(report: dict) -> list[dict]:
    return [f for f in report.get('files') or [] if isinstance(f, dict)]


def detections(report: dict):
    """(posix file, detection dict) for every finding in a check report."""
    for record in report_files(report):
        name = to_posix(record.get('file', ''))
        for det in record.get('detections') or []:
            yield name, det


def rule_counts(report: dict) -> Counter:
    return Counter(det['rule_code'] for _, det in detections(report))


def per100(hits: int, files: int) -> float:
    return hits * 100 / files if files else 0.0


def rate_table(corpora: dict[str, dict]) -> dict[str, dict[str, dict]]:
    """rule -> corpus -> {hits, files, per100}; ``corpora`` maps name -> {files_checked, counts}."""
    table: dict[str, dict[str, dict]] = defaultdict(dict)
    for name, row in corpora.items():
        files = row['files_checked']
        for rule, hits in row['counts'].items():
            table[rule][name] = {'hits': hits, 'files': files, 'per100': per100(hits, files)}
    return dict(table)


def flag_outliers(table: dict[str, dict[str, dict]], factor: float = OUTLIER_FACTOR,
                  min_hits: int = DEFAULT_MIN_HITS) -> list[dict]:
    """Corpora whose rate for a rule exceeds ``factor`` x the median over corpora where it fired."""
    flagged = []
    for rule, cells in sorted(table.items()):
        total = sum(c['hits'] for c in cells.values())
        fired = {k: c['per100'] for k, c in cells.items() if c['hits']}
        if total < min_hits or len(fired) < 2:
            continue
        median = statistics.median(fired.values())
        for name, rate in sorted(fired.items(), key=lambda kv: -kv[1]):
            if rate > factor * median:
                flagged.append({'rule': rule, 'corpus': name, 'per100': rate, 'median_per100': median,
                                'hits': cells[name]['hits'], 'total_hits': total})
    return flagged


def language_rollup(corpora: dict[str, dict]) -> dict[str, dict]:
    """language -> {files, rules: {rule: {hits, per100}}}, summing the corpora of one manifest language."""
    out: dict[str, dict] = {}
    for row in corpora.values():
        lang = out.setdefault(row['language'], {'files': 0, 'corpora': [], 'hits': Counter()})
        lang['files'] += row['files_checked']
        lang['corpora'].append(row['name'])
        lang['hits'].update(row['counts'])
    return {language: {'files': v['files'], 'corpora': sorted(v['corpora']),
                       'rules': {r: {'hits': h, 'per100': per100(h, v['files'])}
                                 for r, h in sorted(v['hits'].items())}}
            for language, v in sorted(out.items())}


# ---------------------------------------------------------------- invariants

def self_line_violations(report: dict) -> dict:
    """Duplicate-style findings that name their own line as the earlier occurrence.

    Returns {'checked': {rule: n}, 'violations': [...]}; an unparsable pointer is a violation too.
    """
    checked: Counter = Counter()
    violations = []
    for file, det in detections(report):
        pattern = POINTER_PATTERNS.get(det['rule_code'])
        if pattern is None:
            continue
        checked[det['rule_code']] += 1
        match = pattern.search(det.get('message', ''))
        base = {'rule': det['rule_code'], 'file': file, 'line': det.get('line'), 'message': det.get('message')}
        if match is None:
            violations.append({**base, 'kind': 'no-pointer'})
        elif int(match.group(1)) == det.get('line'):
            violations.append({**base, 'kind': 'self-line', 'pointer': int(match.group(1))})
    return {'checked': dict(checked), 'violations': violations}


def cycle_members(groups: list[list[str]]) -> set[str]:
    return {to_posix(p) for group in groups for p in group}


def is_load_order_path(path: str) -> bool:
    return load_order_cycle_extension(PurePosixPath(path).suffix)


def i002_circular_violations(report: dict, groups: list[list[str]],
                             is_load_order: Callable[[str], bool] = is_load_order_path) -> dict:
    """Compare files with an I002 finding to the members of ``?circular`` cycle groups.

    Expected: findings == judged load-order members, one each. A member that ``check`` marks skipped
    or errored is unjudged (disclosed in ``unjudged``); a member with no finding, a finding off every
    group, a finding in a language the gate excludes, or two findings on a file are violations.
    """
    members = cycle_members(groups)
    expected = {p for p in members if is_load_order(p)}
    status = {to_posix(r.get('file', '')): r.get('status') for r in report_files(report)}
    unjudged = sorted(p for p in expected if status.get(p) in UNJUDGED_STATUSES)
    found = Counter(file for file, det in detections(report) if det['rule_code'] == 'I002')
    violations = []
    for path in sorted(expected - set(unjudged) - set(found)):
        violations.append({'kind': 'member-without-finding', 'file': path})
    for path in sorted(set(found) - expected):
        why = 'finding-outside-groups' if path not in members else 'finding-in-gated-language'
        violations.append({'kind': why, 'file': path})
    for path in sorted(p for p, n in found.items() if n > 1):
        violations.append({'kind': 'several-findings', 'file': path, 'count': found[path]})
    return {'groups': len(groups), 'members': len(members), 'load_order_members': len(expected),
            'unjudged': unjudged, 'files_with_i002': len(found), 'violations': violations}


# ---------------------------------------------------------------- measurement

Runner = Callable[[list[str], int], subprocess.CompletedProcess]


def run_reveal(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """reveal as a subprocess of this interpreter; the disk cache is off unless the caller set it."""
    env = dict(os.environ)
    env.setdefault('REVEAL_DISK_CACHE', '0')
    return subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True, text=True,
                          encoding='utf-8', timeout=timeout, env=env)


def run_json(args: list[str], timeout: int, runner: Runner) -> tuple[dict, int, float]:
    """Run reveal and parse its JSON; any undocumented exit, timeout or bad JSON is a failed measurement."""
    started = time.monotonic()
    try:
        done = runner(args, timeout)
    except subprocess.TimeoutExpired as exc:
        raise MeasurementFailed(f'timed out after {timeout}s: reveal {" ".join(args[:2])}') from exc
    except OSError as exc:
        raise MeasurementFailed(f'could not start reveal: {exc.strerror}') from exc
    seconds = time.monotonic() - started
    if done.returncode not in DOCUMENTED_EXITS:
        raise MeasurementFailed(f'exit {done.returncode} (documented: {DOCUMENTED_EXITS}): '
                                f'{(done.stderr or "").strip()[:300]}')
    try:
        data = json.loads(done.stdout)
    except ValueError as exc:
        raise MeasurementFailed(f'exit {done.returncode} but stdout is not JSON ({exc})') from exc
    if not isinstance(data, dict):
        raise MeasurementFailed('JSON result is not an object')
    return data, done.returncode, seconds


def measure_check(root: Path, timeout: int, runner: Runner) -> tuple[dict, dict]:
    report, code, seconds = run_json(['check', str(root), '--format', 'json'], timeout, runner)
    summary = report.get('summary') or {}
    if summary.get('items_truncated'):
        raise MeasurementFailed('check output is presentation-truncated: counts would be cut')
    if not isinstance(summary.get('files_checked'), int):
        raise MeasurementFailed('check summary has no files_checked')
    return report, {'exit_code': code, 'seconds': round(seconds, 1), 'files_checked': summary['files_checked'],
                    'files_errored': summary.get('files_errored') or 0,
                    'files_degraded': summary.get('files_degraded') or 0,
                    'total_issues': summary.get('total_issues') or 0,
                    'scan_disclosures': summary.get('scan_disclosures') or []}


def measure_circular(root: Path, timeout: int, runner: Runner) -> tuple[list[list[str]], dict]:
    data, code, seconds = run_json([f'imports://{to_posix(root)}?circular', '--format', 'json'], timeout, runner)
    groups = data.get('cycles')
    if not isinstance(groups, list):
        raise MeasurementFailed('imports ?circular result has no cycles list')
    return groups, {'exit_code': code, 'seconds': round(seconds, 1), 'count': data.get('count')}


def measure_corpus(entry: dict, root: Path, timeout: int, runner: Runner) -> dict:
    """One corpus: pin check, check run, ?circular run, both invariants. Raises MeasurementFailed."""
    name = corpus_key(entry)
    try:
        source_identity(root, entry['sha'])
    except (ValueError, subprocess.SubprocessError, OSError) as exc:
        raise MeasurementFailed(f'pin check: {exc}') from exc
    report, check = measure_check(root, timeout, runner)
    groups, circular = measure_circular(root, timeout, runner)
    try:
        source_identity(root, entry['sha'])
    except (ValueError, subprocess.SubprocessError, OSError) as exc:
        raise MeasurementFailed(f'corpus changed during measurement: {exc}') from exc
    return {'name': name, 'language': entry['language'], 'sha': entry['sha'], 'status': 'ok',
            'check': check, 'circular': circular, 'files_checked': check['files_checked'],
            'counts': dict(rule_counts(report)),
            'self_line': self_line_violations(report),
            'i002_circular': i002_circular_violations(report, groups)}


def tracked_bytes(root: Path) -> int:
    """Bytes of git-tracked files that exist in the working tree (a sparse checkout counts what it has)."""
    listing = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True, check=True,
                             timeout=120).stdout
    total = 0
    for raw in listing.split(b'\0'):
        path = root / raw.decode('utf-8', 'surrogateescape') if raw else None
        if path is not None and os.path.lexists(path):
            total += os.lstat(path).st_size
    return total


def select_corpora(manifest: dict, corpus_root: Path, names: list[str], max_source_mb: float) -> tuple[list, list]:
    """(selected [(entry, root)], skipped [{name, reason}]) from the manifest; no second list of names."""
    entries = {corpus_key(e): e for e in manifest['corpora']}
    unknown = sorted(set(names) - set(entries))
    if unknown:
        raise ValueError(f'not in the manifest: {", ".join(unknown)}')
    selected, skipped = [], []
    for name, entry in entries.items():
        if names and name not in names:
            continue
        root = (corpus_root / name).resolve()
        if not root.is_dir():
            skipped.append({'name': name, 'reason': 'not present under --corpus-root'})
        elif not names and tracked_bytes(root) > max_source_mb * 1_000_000:
            skipped.append({'name': name, 'reason': f'tracked source over {max_source_mb:g} MB'})
        else:
            selected.append((entry, root))
    return selected, skipped


def run_census(selected: list, timeout: int, runner: Runner = run_reveal, min_hits: int = DEFAULT_MIN_HITS) -> dict:
    """Measure serially; a failed corpus is recorded as failed and contributes no counts."""
    records, failures = [], []
    for entry, root in selected:
        name = corpus_key(entry)
        print(f'[{name}] start', file=sys.stderr, flush=True)
        try:
            record = measure_corpus(entry, root, timeout, runner)
        except MeasurementFailed as exc:
            failures.append({'name': name, 'reason': str(exc)})
            records.append({'name': name, 'language': entry['language'], 'status': 'failed', 'failure': str(exc)})
            print(f'[{name}] FAILED {exc}', file=sys.stderr, flush=True)
            continue
        records.append(record)
        print(f'[{name}] check exit {record["check"]["exit_code"]} {record["check"]["seconds"]}s, '
              f'circular exit {record["circular"]["exit_code"]} {record["circular"]["seconds"]}s',
              file=sys.stderr, flush=True)
    return assemble(records, failures, min_hits)


def assemble(records: list[dict], failures: list[dict], min_hits: int = DEFAULT_MIN_HITS) -> dict:
    """Pure: roll the per-corpus records into rates, outliers, languages and invariant verdicts."""
    ok = {r['name']: r for r in records if r['status'] == 'ok'}
    table = rate_table(ok)
    self_line = [{'corpus': n, **v} for n, r in ok.items() for v in r['self_line']['violations']]
    circular = [{'corpus': n, **v} for n, r in ok.items() for v in r['i002_circular']['violations']]
    return {'corpora': records, 'failures': failures, 'counting_rules': COUNTING_RULES,
            'rules': table, 'outliers': flag_outliers(table, min_hits=min_hits),
            'by_language': language_rollup(ok),
            'invariants': {'self_line': {'violations': self_line, 'passed': not self_line},
                           'i002_circular': {'violations': circular, 'passed': not circular}}}


def exit_status(result: dict) -> int:
    if result['failures']:
        return 2
    return 0 if all(inv['passed'] for inv in result['invariants'].values()) else 1


# ---------------------------------------------------------------- text table

def format_table(result: dict) -> str:
    rows = [r for r in result['corpora'] if r['status'] == 'ok']
    out = [f"{'corpus':20} {'lang':10} {'files':>6} {'issues':>7} {'rc':>3} {'sec':>6}  top rules (per 100 files)"]
    for r in rows:
        top = ', '.join(f'{rule}={per100(hits, r["files_checked"]):.0f}'
                        for rule, hits in Counter(r['counts']).most_common(5))
        out.append(f"{r['name']:20} {r['language']:10} {r['files_checked']:6} {r['check']['total_issues']:7} "
                   f"{r['check']['exit_code']:3} {r['check']['seconds']:6.1f}  {top}")
    for r in result['corpora']:
        if r['status'] == 'failed':
            out.append(f"{r['name']:20} FAILED: {r['failure']}")
    out += ['', 'Outliers (rate > 5x the median of corpora where the rule fired; reported, not failed)']
    for o in result['outliers']:
        out.append(f"  {o['rule']}: {o['corpus']} {o['per100']:.1f}/100 files vs median {o['median_per100']:.1f} "
                   f"({o['hits']} of {o['total_hits']} hits)")
    if not result['outliers']:
        out.append('  none')
    out += ['', 'Invariants']
    for name, inv in result['invariants'].items():
        out.append(f"  {name}: {'PASS' if inv['passed'] else 'FAIL'} ({len(inv['violations'])} violations)")
        for v in inv['violations']:
            where = f"{v.get('file')}:{v['line']}" if 'line' in v else v.get('file')
            out.append(f"    {v['corpus']} {v['kind']} {v.get('rule', '')} {where}")
    if result['failures']:
        out += ['', 'Failed measurements']
        out += [f"  {f['name']}: {f['reason']}" for f in result['failures']]
    return '\n'.join(out) + '\n'


# ---------------------------------------------------------------- command line

def main(argv: list[str] | None = None, runner: Runner = run_reveal) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--corpus-root', type=Path, default=Path('~/.cache/reveal-corpus').expanduser())
    parser.add_argument('--corpus', action='append', default=[], metavar='NAME',
                        help='measure only this manifest corpus (repeatable); ignores --max-source-mb')
    parser.add_argument('--output', type=Path, required=True, help='JSON result; the text table goes beside it')
    parser.add_argument('--max-source-mb', type=float, default=DEFAULT_MAX_SOURCE_MB)
    parser.add_argument('--min-hits', type=int, default=DEFAULT_MIN_HITS)
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT, help='seconds per reveal call')
    args = parser.parse_args(argv)
    try:
        selected, skipped = select_corpora(_load_manifest(), args.corpus_root, args.corpus, args.max_source_mb)
        identity = implementation_identity()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'Rule census failed: {exc}', file=sys.stderr)
        return 2
    result = run_census(selected, args.timeout, runner, args.min_hits)
    try:
        if identity != implementation_identity():
            result['failures'].append({'name': '*', 'reason': 'reveal implementation changed during measurement'})
    except (OSError, subprocess.SubprocessError) as exc:
        result['failures'].append({'name': '*', 'reason': f'implementation identity unreadable: {exc}'})
    for item in skipped:
        if args.corpus:  # a requested corpus that is missing is a failure, not a quiet skip
            result['failures'].append({'name': item['name'], 'reason': item['reason']})
    result.update({'implementation': identity, 'python': sys.version, 'corpus_root': to_posix(args.corpus_root),
                   'skipped': skipped, 'max_source_mb': args.max_source_mb, 'min_hits': args.min_hits,
                   'exit_status': exit_status(result)})
    table = format_table(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    args.output.with_suffix('.txt').write_text(table, encoding='utf-8')
    sys.stdout.write(table)
    return result['exit_status']


if __name__ == '__main__':
    raise SystemExit(main())
