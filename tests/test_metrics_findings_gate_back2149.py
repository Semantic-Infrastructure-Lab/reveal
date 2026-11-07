"""BACK-2149 S2: `reveal metrics DIR --hotspots --fail-on findings` is the findings gate the hotspots noun had.

Scott's decision (2026-11-06): file quality below 70 or any function complexity above 20 (strictly greater),
computed over the whole analysed population before any --top/--limit/--offset cut and not moved by the
file filters (--min-complexity is metrics' average-complexity filter). The subcommand and the
``metrics://DIR?hotspots=true`` spelling give the same answer and exit. Without --fail-on findings the exit
stays 0. The gate belongs to the hotspots view (imports' findings-view precedent): the default and
provenance views have nothing to gate.
"""
import json

import pytest

from conftest import _run_reveal_direct as run

pytestmark = pytest.mark.component


def _long(n):
    return f'def long{n}():\n' + ''.join(f'    v{i} = {i}\n' for i in range(130)) + '    return v0\n'


def _easy(count):
    return ''.join(f'\n\ndef easy{n}():\n    return {n}\n' for n in range(count))


def _branchy(name, decisions, longs=0):
    """A function of complexity ``decisions`` (one per if, plus one), beside trivial siblings that keep the
    file's average complexity low; with no long function the file is not a ranked hotspot."""
    body = [f'def {name}(x):'] + [f'    if x == {n}:\n        return {n}' for n in range(decisions - 1)]
    body.append('    return -1\n')
    extra = ''.join('\n\n' + _long(n) for n in range(longs))
    return '\n'.join(body) + '\n' + extra + _easy(40 if longs else 12)


def _longs(count):
    """``count`` long, flat functions among many trivial ones: a ranked hotspot (5 per long function) whose
    quality stays at or above 70 for count <= 3."""
    return '\n\n'.join(_long(n) for n in range(count)) + _easy(40)


def _poor_quality():
    """Two long and two deeply nested functions: quality far below 70, no function above complexity 8."""
    deep = 'def deep{n}(x):\n' + ''.join('    ' * (i + 1) + f'for a{i} in x:\n' for i in range(7)) + '    ' * 8 + 'pass\n'
    return '\n\n'.join(part for n in range(2) for part in (deep.format(n=n), _long(n)))


FILES = {
    'clean.py': 'def add(a, b):\n    return a + b\n',
    'edge.py': _branchy('edge', 20),        # complexity exactly 20: not a finding (> 20 is)
    'complex.py': _branchy('hard', 21),     # complexity 21, quality ~98: a finding, never a ranked hotspot
    'poor.py': _poor_quality(),             # quality < 70: a finding, the top ranked hotspot
    'longs.py': _longs(3),                  # quality ~75, complexity 1: no finding, a ranked hotspot (score 15)
    'ranked_complex.py': _branchy('hard', 21, longs=1),  # complexity 21: a finding, ranked below longs.py
}


@pytest.fixture
def make(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def build(*names):
        root = tmp_path / 'proj'
        root.mkdir()
        for name in names:
            (root / name).write_text(FILES[name], encoding='utf-8')
        return 'proj'
    return build


def _both(target, cli=(), query='', fail_on='findings'):
    """The subcommand and the URI spelling, JSON: the same exit and the same has_findings."""
    gate = ['--fail-on', fail_on] if fail_on else []
    a = run('metrics', target, '--hotspots', *cli, *gate, '--format', 'json', '--no-gitignore')
    b = run(f'metrics://{target}?hotspots=true{query}', *gate, '--format', 'json', '--no-gitignore')
    assert a.returncode == b.returncode, (a.stderr, b.stderr)
    da, db = json.loads(a.stdout), json.loads(b.stdout)
    assert da['summary'].get('has_findings') == db['summary'].get('has_findings')
    return a.returncode, da


@pytest.mark.parametrize('names, expected', [
    (('clean.py',), 0),
    (('clean.py', 'edge.py'), 0),
    (('clean.py', 'complex.py'), 1),
    (('clean.py', 'poor.py'), 1),
    (('clean.py', 'edge.py', 'complex.py', 'poor.py'), 1),
])
def test_the_gate_fires_on_quality_below_70_or_complexity_above_20(make, names, expected):
    code, doc = _both(make(*names))
    assert code == expected
    assert doc['summary']['has_findings'] is bool(expected)


def test_a_function_above_20_gates_although_its_file_is_no_ranked_hotspot(make):
    code, doc = _both(make('clean.py', 'complex.py'))
    assert code == 1
    assert doc['hotspots'] == []  # the ranking never shows complex.py; the gate still sees it
    assert {f['file']: f['complexity']['max'] for f in doc['files']} == {'clean.py': 1, 'complex.py': 21}


def test_without_fail_on_findings_the_exit_stays_0(make):
    target = make('clean.py', 'complex.py', 'poor.py')
    for fail_on in (None, 'none'):
        code, doc = _both(target, fail_on=fail_on)
        assert code == 0, fail_on
        assert doc['summary']['has_findings'] is True


def test_the_top_cut_ranks_the_offending_file_below_the_cut(make):
    """Positive control for the cut: uncut, the offending file is in the ranking, second."""
    _, doc = _both(make('longs.py', 'ranked_complex.py'), fail_on=None)
    assert [h['file'] for h in doc['hotspots']] == ['longs.py', 'ranked_complex.py']
    assert doc['hotspots'][0]['quality_score'] >= 70


def test_a_top_cut_that_hides_the_offending_file_still_gates(make):
    code, doc = _both(make('longs.py', 'ranked_complex.py'), ['--top', '1'], '&top=1')
    assert [h['file'] for h in doc['hotspots']] == ['longs.py']
    assert code == 1 and doc['summary']['has_findings'] is True


def test_a_ranked_file_with_no_finding_does_not_gate(make):
    """Negative control: a hotspot is not a finding; longs.py ranks first with quality >= 70 and complexity 1."""
    code, doc = _both(make('longs.py', 'clean.py'), ['--top', '1'], '&top=1')
    assert [h['file'] for h in doc['hotspots']] == ['longs.py']
    assert code == 0 and doc['summary']['has_findings'] is False


@pytest.mark.parametrize('cli, query', [
    (['--limit', '1', '--sort', 'lines'], '&limit=1&sort=lines'),
    (['--limit', '1', '--offset', '0', '--sort', 'lines'], '&limit=1&offset=0&sort=lines'),
    (['--offset', '1', '--sort', '-lines'], '&offset=1&sort=-lines'),
])
def test_a_files_page_that_hides_the_offending_file_still_gates(make, cli, query):
    code, doc = _both(make('clean.py', 'complex.py'), cli, query)
    assert [f['file'] for f in doc['files']] == ['clean.py']  # the page really leaves complex.py out
    assert code == 1 and doc['summary']['has_findings'] is True


@pytest.mark.parametrize('cli, query, kept', [
    (['--min-complexity', '100'], '&min_complexity=100', []),  # metrics' average-complexity filter keeps no file
    (['--max-complexity', '1'], '&max_complexity=1', ['clean.py']),
    (['--min-complexity', '0'], '&min_complexity=0', ['clean.py', 'complex.py']),
])
def test_the_file_filters_do_not_change_the_verdict(make, cli, query, kept):
    code, doc = _both(make('clean.py', 'complex.py'), cli, query)
    assert sorted(f['file'] for f in doc['files']) == kept
    assert code == 1 and doc['summary']['has_findings'] is True


def test_a_clean_population_stays_clean_under_the_same_filters(make):
    """Negative control: a filter cannot make a clean tree gate either."""
    code, doc = _both(make('clean.py', 'edge.py'), ['--min-complexity', '0'], '&min_complexity=0')
    assert code == 0 and doc['summary']['has_findings'] is False


def test_a_single_file_target_gates_on_the_same_predicate(make):
    make('complex.py', 'clean.py')
    code, doc = _both('proj/complex.py')
    assert code == 1 and doc['summary']['has_findings'] is True
    code, doc = _both('proj/clean.py')
    assert code == 0 and doc['summary']['has_findings'] is False


@pytest.mark.parametrize('argv', [
    ['metrics', 'proj'],
    ['metrics://proj'],
    ['metrics', 'proj', '--view', 'provenance'],
    ['metrics://proj?view=provenance'],
])
def test_views_without_the_ranking_have_nothing_to_gate(make, argv):
    """The findings verdict belongs to the hotspots view; asking another view to gate is refused, exit 2
    naming the view that gates, since the gate could never fire (BACK-2528: it exited 0, a false green
    for a CI run that forgot --hotspots). Without --fail-on the view answers, with no has_findings."""
    make('clean.py', 'complex.py', 'poor.py')
    result = run(*argv, '--fail-on', 'findings', '--format', 'json', '--no-gitignore')
    assert result.returncode == 2, result.stderr
    assert 'metrics gates --hotspots' in result.stderr
    assert 'metrics gates --hotspots' in json.loads(result.stdout)['error']
    answered = run(*argv, '--format', 'json', '--no-gitignore')
    assert answered.returncode == 0, answered.stderr
    assert 'has_findings' not in json.loads(answered.stdout).get('summary', {})


def test_the_exit_code_help_names_the_gate():
    result = run('metrics', '--help')
    assert result.returncode == 0
    text = ' '.join(result.stdout.split())
    assert '--fail-on {none,findings}' in text
    assert 'quality below 70' in text and 'complexity above 20' in text


@pytest.mark.parametrize('names, verdict', [(('clean.py', 'complex.py'), 'yes'), (('clean.py', 'edge.py'), 'none')])
def test_text_states_the_verdict_and_its_rule_in_both_spellings(make, names, verdict):
    target = make(*names)
    for argv in (['metrics', target, '--hotspots'], [f'metrics://{target}?hotspots=true']):
        result = run(*argv, '--no-gitignore')
        assert result.returncode == 0, result.stderr
        assert (f'Findings:   {verdict} (a file below quality 70 or a function above complexity 20, '
                'over every analysed file before filters and cuts)') in result.stdout, argv
    assert 'Findings:' not in run('metrics', target, '--no-gitignore').stdout  # no ranking, no verdict
