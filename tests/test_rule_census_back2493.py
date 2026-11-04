"""BACK-2493: the rule census aggregates per corpus and language, flags outliers, and fails on two
oracle-free invariants (no self-line pointer; I002 files == judged ``?circular`` group members).

Everything but the last test group runs on small synthetic check JSON; no corpus is needed.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component
SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load('recall_oracles'); load('recall_gate'); load('fetch_corpus'); load('rule_precision')
census = load('rule_census')


def det(rule, line, message='m'):
    return {'rule_code': rule, 'line': line, 'message': message}


def record(file, *dets, **extra):
    return {'file': file, 'issues': len(dets), 'detections': list(dets), **extra}


def report(*records, files_checked=10, **summary):
    return {'summary': {'files_checked': files_checked, **summary}, 'files': list(records)}


I005_AT_9_OF_3 = "Duplicate import: 'os' (first imported at line 3)"
D001_AT_30_OF_12 = "Duplicate function detected: 'b' identical to 'a' (line 12)"


# ---------------------------------------------------------------- rates and outliers

def table_of(rates):
    """rule -> corpus -> cell, from {corpus: (files, {rule: hits})}."""
    corpora = {n: {'files_checked': f, 'counts': c} for n, (f, c) in rates.items()}
    return census.rate_table(corpora)


def test_rate_is_findings_per_100_files():
    table = table_of({'a': (200, {'X': 50})})
    assert table['X']['a'] == {'hits': 50, 'files': 200, 'per100': 25.0}
    assert census.per100(5, 0) == 0.0


def test_outlier_above_five_times_the_median_of_corpora_where_the_rule_fired():
    table = table_of({'a': (100, {'X': 10}), 'b': (100, {'X': 10}), 'c': (100, {'X': 10}),
                      'd': (100, {'X': 60}), 'e': (100, {'Y': 99})})
    flagged = census.flag_outliers(table, min_hits=1)
    assert [(o['rule'], o['corpus']) for o in flagged if o['rule'] == 'X'] == [('X', 'd')]
    (hit,) = [o for o in flagged if o['rule'] == 'X']
    assert hit['median_per100'] == 10.0 and hit['hits'] == 60 and hit['total_hits'] == 90


def test_exactly_five_times_the_median_is_not_an_outlier():
    table = table_of({'a': (100, {'X': 10}), 'b': (100, {'X': 10}), 'c': (100, {'X': 50})})
    assert census.flag_outliers(table, min_hits=1) == []


def test_a_corpus_where_the_rule_never_fired_does_not_pull_the_median_down():
    # Counting zeros would give median 0 and make every firing corpus an outlier.
    table = table_of({'a': (100, {'X': 10}), 'b': (100, {'X': 12}), 'c': (100, {}), 'd': (100, {}), 'e': (100, {})})
    assert census.flag_outliers(table, min_hits=1) == []


def test_a_rule_below_min_hits_in_total_is_not_flagged():
    table = table_of({'a': (100, {'X': 10}), 'b': (100, {'X': 10}), 'c': (100, {'X': 10}), 'd': (100, {'X': 90})})
    assert census.flag_outliers(table, min_hits=200) == []
    assert [o['corpus'] for o in census.flag_outliers(table, min_hits=50)] == ['d']


def test_language_rollup_sums_the_corpora_of_one_language():
    corpora = {'rust': {'name': 'rust', 'language': 'rust', 'files_checked': 100, 'counts': {'X': 10}},
               'rust-ripgrep': {'name': 'rust-ripgrep', 'language': 'rust', 'files_checked': 100, 'counts': {'X': 30}},
               'lua': {'name': 'lua', 'language': 'lua', 'files_checked': 50, 'counts': {'X': 5}}}
    out = census.language_rollup(corpora)
    assert out['rust']['rules']['X'] == {'hits': 40, 'per100': 20.0}
    assert out['rust']['corpora'] == ['rust', 'rust-ripgrep']
    assert out['lua']['rules']['X']['per100'] == 10.0


# ---------------------------------------------------------------- invariant 1: self-line

def test_a_planted_self_line_i005_finding_fails_the_invariant():
    planted = det('I005', 7, "Duplicate import: 'use crate::{' (first imported at line 7)")
    out = census.self_line_violations(report(record('src/a.rs', planted)))
    assert out['checked'] == {'I005': 1}
    assert [(v['kind'], v['file'], v['line'], v['pointer']) for v in out['violations']] == [
        ('self-line', 'src/a.rs', 7, 7)]


def test_a_planted_self_line_d001_finding_fails_the_invariant():
    planted = det('D001', 30, "Duplicate function detected: 'b' identical to 'a' (line 30)")
    out = census.self_line_violations(report(record('a.py', planted)))
    assert [(v['rule'], v['kind']) for v in out['violations']] == [('D001', 'self-line')]


def test_a_planted_self_line_d002_finding_fails_the_invariant():
    planted = det('D002', 5, "Near-duplicate function: 'b' ~91% similar to 'a' (line 5)")
    out = census.self_line_violations(report(record('a.py', planted)))
    assert [(v['rule'], v['kind']) for v in out['violations']] == [('D002', 'self-line')]


def test_earlier_occurrence_on_another_line_passes():
    out = census.self_line_violations(report(
        record('a.py', det('I005', 9, I005_AT_9_OF_3), det('D001', 30, D001_AT_30_OF_12))))
    assert out['violations'] == [] and out['checked'] == {'I005': 1, 'D001': 1}


def test_a_statement_with_parentheses_and_digits_still_parses():
    msg = "Duplicate import: 'from x import (a, b)  # line 4' (first imported at line 2)"
    assert census.self_line_violations(report(record('a.py', det('I005', 4, msg))))['violations'] == []
    own = "Duplicate import: 'import x  # (first imported at line 2)' (first imported at line 4)"
    out = census.self_line_violations(report(record('a.py', det('I005', 4, own))))
    assert [v['kind'] for v in out['violations']] == ['self-line']


def test_a_pointer_rule_message_without_a_pointer_fails_rather_than_passing_vacuously():
    out = census.self_line_violations(report(record('a.py', det('I005', 4, 'Duplicate import: reworded'))))
    assert [v['kind'] for v in out['violations']] == ['no-pointer']


def test_other_rules_are_not_read_for_pointers():
    other = det('C902', 3, 'Function is too long: describe(line 3) (140 lines, max: 100)')
    out = census.self_line_violations(report(record('a.py', other)))
    assert out == {'checked': {}, 'violations': []}


def test_pointer_patterns_match_what_the_rules_emit(tmp_path):
    """Positive control on the real rules: the patterns parse I005 and D001 output, and the
    pointer is an earlier line. Not a test of the rules' correctness."""
    body = '    x = 1\n    y = 2\n    z = x + y\n    w = z * 2\n    return w + x + y\n'
    (tmp_path / 'm.py').write_text(
        f'import os\nimport os\n\ndef first(a):\n{body}\ndef second(a):\n{body}', encoding='utf-8')
    run = _run_reveal_direct('check', tmp_path, '--select', 'I005,D001', '--format', 'json')
    data = json.loads(run.stdout)
    found = {d['rule_code']: d for r in data['files'] for d in r.get('detections') or []}
    assert set(found) == {'I005', 'D001'}, found
    out = census.self_line_violations({'summary': {}, 'files': [{'file': 'm.py', 'detections': list(found.values())}]})
    assert out['checked'] == {'I005': 1, 'D001': 1} and out['violations'] == []
    for rule, d in found.items():
        pointer = int(census.POINTER_PATTERNS[rule].search(d['message']).group(1))
        assert pointer < d['line'], (rule, d)


# ---------------------------------------------------------------- invariant 2: I002 vs ?circular

def i002_report(*files, extra=()):
    return report(*[record(f, det('I002', 1, 'cycle')) for f in files], *extra)


GROUPS = [['a.py', 'b.py', 'c.py'], ['x.ts', 'y.ts']]


def test_findings_equal_to_group_members_pass():
    out = census.i002_circular_violations(i002_report('a.py', 'b.py', 'c.py', 'x.ts', 'y.ts'), GROUPS)
    assert out['violations'] == []
    assert (out['groups'], out['members'], out['load_order_members'], out['files_with_i002']) == (2, 5, 5, 5)


def test_an_i002_file_missing_from_a_cycle_group_fails():
    """The group has b.py, check never reported it (the pre-BACK-2156 miss: tsx 362 of 364)."""
    out = census.i002_circular_violations(i002_report('a.py', 'c.py', 'x.ts', 'y.ts'), GROUPS)
    assert out['violations'] == [{'kind': 'member-without-finding', 'file': 'b.py'}]


def test_a_finding_outside_every_group_fails():
    out = census.i002_circular_violations(i002_report('a.py', 'b.py', 'c.py', 'x.ts', 'y.ts', 'stray.py'), GROUPS)
    assert out['violations'] == [{'kind': 'finding-outside-groups', 'file': 'stray.py'}]


def test_two_findings_on_one_file_fail():
    rep = report(record('a.py', det('I002', 1, 'c'), det('I002', 2, 'c')), record('b.py', det('I002', 1, 'c')),
                 record('c.py', det('I002', 1, 'c')), record('x.ts', det('I002', 1, 'c')), record('y.ts', det('I002', 1, 'c')))
    out = census.i002_circular_violations(rep, GROUPS)
    assert out['violations'] == [{'kind': 'several-findings', 'file': 'a.py', 'count': 2}]


def test_members_in_a_language_the_gate_excludes_carry_no_finding():
    groups = [['src/a.rs', 'src/b.rs'], ['p.py', 'q.py']]
    assert census.i002_circular_violations(i002_report('p.py', 'q.py'), groups)['violations'] == []
    leak = census.i002_circular_violations(i002_report('p.py', 'q.py', 'src/a.rs'), groups)
    assert leak['violations'] == [{'kind': 'finding-in-gated-language', 'file': 'src/a.rs'}]


def test_a_stub_member_is_not_expected_to_carry_a_finding():
    assert census.is_load_order_path('pkg/m.py') and census.is_load_order_path('a/b.tsx')
    assert not census.is_load_order_path('pkg/m.pyi') and not census.is_load_order_path('src/lib.rs')


def test_a_member_check_skipped_is_disclosed_not_failed_but_a_clean_one_is_failed():
    skipped = record('b.py', status='skipped', detail='auto-generated file')
    rep = i002_report('a.py', 'c.py', 'x.ts', 'y.ts', extra=[skipped])
    out = census.i002_circular_violations(rep, GROUPS)
    assert out['violations'] == [] and out['unjudged'] == ['b.py']
    # Negative control: the same file is checked and clean (no record at all) -> a real miss.
    out = census.i002_circular_violations(i002_report('a.py', 'c.py', 'x.ts', 'y.ts'), GROUPS)
    assert [v['file'] for v in out['violations']] == ['b.py']
    # A warning record (parsed with errors) was still judged, so it does not excuse the member.
    warned = record('b.py', status='warning', detail='parse errors')
    out = census.i002_circular_violations(i002_report('a.py', 'c.py', 'x.ts', 'y.ts', extra=[warned]), GROUPS)
    assert [v['file'] for v in out['violations']] == ['b.py']


def test_backslash_spelled_paths_compare_equal():
    out = census.i002_circular_violations(i002_report('pkg\\a.py', 'pkg\\b.py'), [['pkg/a.py', 'pkg/b.py']])
    assert out['violations'] == []


# ---------------------------------------------------------------- failed measurement is not a zero

def completed(code, stdout='', stderr=''):
    return subprocess.CompletedProcess(['reveal'], code, stdout=stdout, stderr=stderr)


def test_an_undocumented_exit_is_a_failed_measurement():
    with pytest.raises(census.MeasurementFailed, match='exit 2'):
        census.run_json(['check', 'x'], 5, lambda a, t: completed(2, '{"summary": {}, "files": []}', 'usage'))


def test_exit_3_scan_incomplete_is_documented_and_recorded():
    data, code, _ = census.run_json(['check', 'x'], 5, lambda a, t: completed(3, '{"files": []}'))
    assert code == 3 and data == {'files': []}


def test_timeout_and_unparsable_output_are_failures():
    def slow(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)
    with pytest.raises(census.MeasurementFailed, match='timed out'):
        census.run_json(['check', 'x'], 5, slow)
    with pytest.raises(census.MeasurementFailed, match='not JSON'):
        census.run_json(['check', 'x'], 5, lambda a, t: completed(0, 'oops'))


def test_a_presentation_truncated_check_is_a_failure(tmp_path):
    runner = lambda a, t: completed(1, json.dumps(report(items_truncated=True)))  # noqa: E731
    with pytest.raises(census.MeasurementFailed, match='truncated'):
        census.measure_check(tmp_path, 5, runner)


def git(root, *args):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-C', str(root), *args],
                   check=True, capture_output=True, timeout=60)


@pytest.fixture
def pinned(tmp_path):
    """A one-commit git repo as a pinned corpus -> (entry, root)."""
    root = tmp_path / 'corp'
    root.mkdir()
    (root / 'a.py').write_text('x = 1\n', encoding='utf-8')
    git(root, 'init', '-q')
    git(root, 'add', 'a.py')
    git(root, 'commit', '-q', '-m', 'pin')
    sha = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                         text=True, encoding='utf-8', timeout=60).stdout.strip()
    return {'id': 'corp', 'language': 'python', 'repo': 'x', 'sha': sha}, root


def fake_runner(check_report, groups=(), check_code=1, circular_code=0, fail_on=None):
    calls = []

    def runner(args, timeout):
        calls.append(args)
        if fail_on and args[0].startswith(fail_on):
            # A well-formed zero-finding body behind exit 2: only the exit code says it failed.
            return completed(2, json.dumps(check_report), 'usage error')
        if args[0] == 'check':
            return completed(check_code, json.dumps(check_report))
        return completed(circular_code, json.dumps({'cycles': [list(g) for g in groups], 'count': len(groups)}))
    runner.calls = calls
    return runner


def test_a_failed_corpus_exit_is_a_failure_and_no_zero_row(pinned):
    entry, root = pinned
    runner = fake_runner(report(record('a.py', det('C901', 1))), fail_on='check')
    result = census.run_census([(entry, root)], 5, runner)
    assert [f['name'] for f in result['failures']] == ['corp']
    assert 'exit 2' in result['failures'][0]['reason']
    assert result['rules'] == {} and result['by_language'] == {}
    assert [r['status'] for r in result['corpora']] == ['failed']
    assert census.exit_status(result) == 2


def test_a_pin_mismatch_is_a_failure_before_reveal_runs(pinned):
    entry, root = pinned
    runner = fake_runner(report())
    result = census.run_census([({**entry, 'sha': '0' * 40}, root)], 5, runner)
    assert 'pin check' in result['failures'][0]['reason'] and runner.calls == []


def test_a_modified_corpus_is_a_failure(pinned):
    entry, root = pinned
    (root / 'a.py').write_text('x = 2\n', encoding='utf-8')
    result = census.run_census([(entry, root)], 5, fake_runner(report()))
    assert 'modified' in result['failures'][0]['reason']


def test_one_failed_corpus_does_not_hide_the_others(pinned):
    entry, root = pinned
    ok = fake_runner(report(record('a.py', det('C901', 1)), files_checked=4))
    result = census.run_census([(entry, root)], 5, ok)
    assert result['failures'] == [] and result['rules']['C901']['corp']['per100'] == 25.0
    assert census.exit_status(result) == 0


def test_a_violation_exits_1_and_names_the_finding(pinned):
    entry, root = pinned
    bad = report(record('a.py', det('I005', 7, "Duplicate import: 'u' (first imported at line 7)")))
    result = census.run_census([(entry, root)], 5, fake_runner(bad))
    assert census.exit_status(result) == 1
    (v,) = result['invariants']['self_line']['violations']
    assert (v['corpus'], v['file'], v['line'], v['kind']) == ('corp', 'a.py', 7, 'self-line')
    assert 'corp self-line I005 a.py:7' in census.format_table(result)


# ---------------------------------------------------------------- command line and selection

def manifest(*names):
    return {'corpora': [{'id': n, 'language': n.split('-')[0], 'repo': 'x', 'sha': 'f' * 40} for n in names]}


def test_selection_skips_absent_and_oversize_and_never_hand_lists_names(tmp_path, monkeypatch):
    for n in ('small', 'huge'):
        (tmp_path / n).mkdir()
    monkeypatch.setattr(census, 'tracked_bytes', lambda root: 500_000_000 if root.name == 'huge' else 1_000)
    selected, skipped = census.select_corpora(manifest('small', 'huge', 'gone'), tmp_path, [], 100)
    assert [e['id'] for e, _ in selected] == ['small']
    assert {s['name']: s['reason'] for s in skipped} == {'huge': 'tracked source over 100 MB',
                                                          'gone': 'not present under --corpus-root'}
    selected, _ = census.select_corpora(manifest('small', 'huge'), tmp_path, ['huge'], 100)
    assert [e['id'] for e, _ in selected] == ['huge']  # an explicit name ignores the size cap
    with pytest.raises(ValueError, match='not in the manifest: nope'):
        census.select_corpora(manifest('small'), tmp_path, ['nope'], 100)


def test_tracked_bytes_counts_tracked_files_only(pinned):
    _entry, root = pinned
    (root / 'untracked.bin').write_bytes(b'0' * 5000)
    assert census.tracked_bytes(root) == len('x = 1\n')


def run_main(tmp_path, monkeypatch, entry, runner, *extra):
    monkeypatch.setattr(census, '_load_manifest', lambda: {'corpora': [entry]})
    monkeypatch.setattr(census, 'implementation_identity', lambda: {'head': 'h'})
    out = tmp_path / 'out' / 'census.json'
    code = census.main(['--corpus-root', str(tmp_path), '--output', str(out), *extra], runner=runner)
    return code, out


def test_main_writes_json_and_table_and_exits_0_when_clean(pinned, tmp_path, monkeypatch, capsys):
    entry, root = pinned
    rep = report(record('a.py', det('I002', 1, 'c'), det('C901', 2)), record('b.py', det('I002', 1, 'c')), files_checked=2)
    code, out = run_main(tmp_path, monkeypatch, entry, fake_runner(rep, groups=[['a.py', 'b.py']]), '--corpus', 'corp')
    data = json.loads(out.read_text(encoding='utf-8'))
    assert code == 0 and data['exit_status'] == 0 and data['implementation'] == {'head': 'h'}
    assert data['rules']['C901']['corp']['per100'] == 50.0
    assert data['invariants']['i002_circular']['passed'] and data['invariants']['self_line']['passed']
    assert out.with_suffix('.txt').read_text(encoding='utf-8') == capsys.readouterr().out
    assert 'self_line: PASS' in out.with_suffix('.txt').read_text(encoding='utf-8')


def test_main_exits_1_for_a_missing_i002_member(pinned, tmp_path, monkeypatch):
    entry, _root = pinned
    rep = report(record('a.py', det('I002', 1, 'c')), files_checked=2)
    code, out = run_main(tmp_path, monkeypatch, entry, fake_runner(rep, groups=[['a.py', 'b.py']]), '--corpus', 'corp')
    assert code == 1
    (v,) = json.loads(out.read_text(encoding='utf-8'))['invariants']['i002_circular']['violations']
    assert (v['corpus'], v['kind'], v['file']) == ('corp', 'member-without-finding', 'b.py')


def test_main_exits_2_for_a_failed_corpus_a_missing_corpus_and_an_unknown_name(pinned, tmp_path, monkeypatch):
    entry, _root = pinned
    code, out = run_main(tmp_path, monkeypatch, entry, fake_runner(report(), fail_on='check'), '--corpus', 'corp')
    assert code == 2 and json.loads(out.read_text(encoding='utf-8'))['failures'][0]['name'] == 'corp'
    gone = {**entry, 'id': 'gone'}
    code, out = run_main(tmp_path, monkeypatch, gone, fake_runner(report()), '--corpus', 'gone')
    assert code == 2 and 'not present' in json.loads(out.read_text(encoding='utf-8'))['failures'][0]['reason']
    code, _ = run_main(tmp_path, monkeypatch, entry, fake_runner(report()), '--corpus', 'nope')
    assert code == 2


def test_output_is_required():
    with pytest.raises(SystemExit) as exc:
        census.main([])
    assert exc.value.code == 2
