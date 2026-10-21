"""BACK-2146 slice 1: `reveal metrics PATH` and `metrics://PATH` are two spellings of one answer.

metrics is a declared noun (PARAM_SPECS on MetricsAdapter, an entry in COMMANDS), so both spellings run
the one declared execution owner: equal parsed JSON, the same exit code, and provenance that differs
only in ``execution.command`` (surface program section 9). The legacy ``stats://`` spelling keeps
answering through the legacy URI route and must still equal the new one.
"""
import copy
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import declared_adapter_class

pytestmark = pytest.mark.component

BUSY = 'def busy(x):\n' + ''.join(f'    if x == {n}:\n        x += {n}\n' for n in range(14)) + '    return x\n'


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'app.py').write_text('def add(a, b):\n    return a + b\n', encoding='utf-8')
    (root / 'pkg' / 'busy.py').write_text(BUSY, encoding='utf-8')
    (root / 'pkg' / 'small.py').write_text('X = 1\n\n\ndef one():\n    return X\n', encoding='utf-8')
    return root


def equal_answers(noun_spelling, left, right):
    """Only the command spelling may differ; a changed count or a dropped diagnostic must not pass."""
    a, b = copy.deepcopy(left), copy.deepcopy(right)
    if 'execution' in a:
        assert a['execution']['command'].startswith('reveal metrics ')
        assert b['execution']['command'].startswith('reveal metrics://')
        del a['execution']['command'], b['execution']['command']
    assert a == b, noun_spelling


# (argv after `metrics proj`, query after `metrics://proj`)
CASES = [
    ([], ''),
    (['--hotspots'], '?hotspots=true'),
    (['--hotspots', '--top', '1'], '?hotspots=true&top=1'),
    (['--hotspots', '--top', '0'], '?hotspots=true&top=0'),
    (['--hotspots', '--no-churn'], '?hotspots=true&churn=false'),
    (['--min-lines', '5'], '?min_lines=5'),
    (['--max-lines', '30'], '?max_lines=30'),
    (['--min-complexity', '5.5'], '?min_complexity=5.5'),
    (['--max-complexity', '20'], '?max_complexity=20'),
    (['--min-functions', '1'], '?min_functions=1'),
    (['--code-only'], '?code_only=true'),
    (['--summary-only'], '?summary_only=true'),
    (['--sort', '-lines'], '?sort=-lines'),
    (['--sort', 'lines', '--limit', '2'], '?sort=lines&limit=2'),
    (['--sort', 'lines', '--limit', '1', '--offset', '1'], '?sort=lines&limit=1&offset=1'),
    (['--view', 'provenance'], '?view=provenance'),
]
IDS = [' '.join(cli) or 'default' for cli, _ in CASES]


def test_metrics_is_a_declared_noun():
    from reveal.adapters.stats import MetricsAdapter
    assert COMMANDS['metrics'].declared_adapter == 'metrics'
    assert declared_adapter_class('metrics') is MetricsAdapter


@pytest.mark.parametrize('provenance', [False, True])
@pytest.mark.parametrize('cli,query', CASES, ids=IDS)
def test_json_answers_match(project, cli, query, provenance):
    flags = ['--format', 'json', '--no-gitignore'] + (['--provenance'] if provenance else [])
    a = run('metrics', 'proj', *cli, *flags)
    b = run(f'metrics://proj{query}', *flags)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left.get('type') and (left.get('files') or left.get('summary')), 'an empty answer compares equal vacuously'
    if provenance:
        assert left['execution']['command'].startswith('reveal metrics ')
        assert right['execution']['command'].startswith('reveal metrics://')
    equal_answers(query, left, right)
    assert a.stderr == b.stderr


@pytest.mark.parametrize('cli,query', CASES, ids=IDS)
def test_text_output_matches(project, cli, query):
    a = run('metrics', 'proj', *cli, '--no-gitignore')
    b = run(f'metrics://proj{query}', '--no-gitignore')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout.strip() and a.stdout == b.stdout
    assert a.stderr == b.stderr


@pytest.mark.parametrize('cli,query', [([], ''), (['--hotspots'], '?hotspots=true')])
def test_a_file_target_answers_alike(project, cli, query):
    a = run('metrics', 'proj/pkg/busy.py', *cli, '--format', 'json')
    b = run(f'metrics://proj/pkg/busy.py{query}', '--format', 'json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['type'] == 'stats_file'
    assert left == right


def test_a_directory_and_a_provenance_view_keep_their_own_result_types(project):
    types = {tuple(argv): json.loads(run(*argv, '--format', 'json').stdout)['type'] for argv in (
        ('metrics', 'proj'), ('metrics', 'proj', '--view', 'provenance'), ('metrics://proj',))}
    assert types == {('metrics', 'proj'): 'stats_summary',
                     ('metrics', 'proj', '--view', 'provenance'): 'classify_report',
                     ('metrics://proj',): 'stats_summary'}


@pytest.mark.parametrize('flags,message', [
    (['--top', '-1'], 'top'),
    (['--min-lines', 'abc'], 'min_lines'),
    (['--view', 'everything'], 'view'),
    (['--limit', '-1'], 'limit'),
])
def test_a_bad_value_is_rejected_alike(project, flags, message):
    query = '?' + '&'.join(f"{flag[2:].replace('-', '_')}={value}"
                           for flag, value in zip(flags[::2], flags[1::2]))
    a = run('metrics', 'proj', *flags, '--format', 'json')
    b = run(f'metrics://proj{query}', '--format', 'json')
    assert a.returncode == b.returncode == 2, (a.stderr, b.stderr)
    assert a.stdout == b.stdout
    assert message in a.stdout + a.stderr


def test_a_missing_path_is_rejected_alike(project):
    a = run('metrics', 'absent', '--format', 'json')
    b = run('metrics://absent', '--format', 'json')
    assert a.returncode == b.returncode == 2, (a.stderr, b.stderr)
    assert a.stdout == b.stdout and a.stderr == b.stderr


def test_the_findings_gate_is_not_declared_for_metrics(project):
    """metrics reports a count; it has no findings gate, so --fail-on findings is a usage error in both spellings."""
    a = run('metrics', 'proj', '--fail-on', 'findings')
    b = run('metrics://proj', '--fail-on', 'findings')
    assert a.returncode == b.returncode == 2
    assert a.stderr == b.stderr and 'not supported' in a.stderr


def test_operator_filters_still_answer_on_the_uri(project):
    """Positive control: `lines>N` is URI-only; declaring the named parameters must not drop it."""
    every = json.loads(run('metrics://proj', '--format', 'json', '--no-gitignore').stdout)
    lines = {row['file']: row['lines']['total'] for row in every['files']}
    assert len(set(lines.values())) > 1, 'the fixture needs files of different sizes'
    cut = sorted(lines.values())[0]
    kept = json.loads(run(f'metrics://proj?lines>{cut}', '--format', 'json', '--no-gitignore').stdout)
    assert sorted(row['file'] for row in kept['files']) == sorted(f for f, n in lines.items() if n > cut)


@pytest.mark.parametrize('query', ['', '?hotspots=true', '?view=provenance', '?min_lines=5&sort=-lines'])
def test_the_retired_stats_scheme_still_equals_metrics(project, query):
    new = run(f'metrics://proj{query}', '--format', 'json', '--no-gitignore')
    old = run(f'stats://proj{query}', '--format', 'json', '--no-gitignore')
    assert new.returncode == old.returncode == 0, (new.stderr, old.stderr)
    left, right = json.loads(new.stdout), json.loads(old.stdout)
    for doc in (left, right):
        doc.pop('source', None)
        meta = doc.setdefault('meta', {})
        warnings = [w for w in meta.get('warnings', []) if w.get('code') != 'retired_spelling']
        if warnings:
            meta['warnings'] = warnings
        else:
            meta.pop('warnings', None)
        if not meta:
            doc.pop('meta')
    assert left == right
