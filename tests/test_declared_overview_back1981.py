"""Ordinary overview retains declared execution, delivery and proof contracts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.overview import OverviewAdapter


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    for n in range(7):
        folder = root / f'pkg{n}'
        folder.mkdir(parents=True)
        (folder / 'a.py').write_text('VALUE=1\n', encoding='utf-8')
    return root


def requests(cli=(), query=''):
    return ['overview', 'proj', *cli], ['overview://proj' + ('?' + query if query else '')]


def equal_answers(left, right):
    left, right = deepcopy(left), deepcopy(right)
    if 'execution' in left:
        del left['execution']['command'], right['execution']['command']
    assert left == right


@pytest.mark.parametrize('cli,query,count', [([], '', 5), (['--top', '0'], 'top=0', 0),
    (['--top', '3.0'], 'top=3.0', 3), (['--top', '3e0'], 'top=3e0', 3)])
@pytest.mark.parametrize('provenance', [False, True])
def test_exact_parity_bounded_map_and_provenance(project, cli, query, count, provenance):
    flags = ['--format', 'json'] + (['--provenance'] if provenance else [])
    left, right = requests(cli, query)
    a, b = run(*left, *flags), run(*right, *flags)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    first, second = json.loads(a.stdout), json.loads(b.stdout)
    assert first['map']['components']['returned'] == count
    assert first['map']['components']['total'] == 7
    if provenance:
        assert first['execution']['command'] == ' '.join(['reveal', *left, *flags])
        assert second['execution']['command'] == ' '.join(['reveal', *right, *flags])
    equal_answers(first, second)


@pytest.mark.parametrize('transport', ['command', 'uri'])
def test_artifacts_and_fields_keep_canonical_identity(project, transport):
    argv = requests()[transport == 'uri']
    artifact = project / 'answer.json'
    result = run(*argv, '--format', 'json', '--fields', 'scope', '--output', f'json={artifact}',
                 '--fail-on', 'none')
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body['type'] == 'overview' and body['scope']['total_code_files'] == 7
    assert 'map' not in body
    assert not artifact.exists()  # Same-format output is the existing disclosed no-op.
    text = run(*argv, '--output', f'json={artifact}')
    assert text.returncode == 0, text.stderr
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert saved['type'] == 'overview' and saved['scope']['total_code_files'] == 7
    result = run(*argv, '--fail-on', 'findings')
    assert result.returncode == 2


def test_postprocessing_cannot_manufacture_recovery(project, monkeypatch):
    from reveal.analyzers.imports import service
    clean = OverviewAdapter(str(project)).get_structure()
    def failed(scope, **kwargs):
        raise OSError('required graph unavailable')
    monkeypatch.setattr(service, 'analyze', failed)
    monkeypatch.setattr(OverviewAdapter, 'post_process', lambda self, result, args: deepcopy(clean), raising=False)
    result = run('overview', 'proj', '--format', 'json', '--fields', 'scope')
    assert result.returncode == 3


@pytest.mark.parametrize('skip', [False, True])
def test_owner_answer_requirement_does_not_consume_bound_query(project, skip):
    from reveal.utils.query_parser import collect_query_keys
    result = OverviewAdapter(str(project), 'no_imports=true' if skip else '').get_structure()
    with collect_query_keys() as keys:
        adapter = OverviewAdapter(str(project), params={'no_imports': skip})
        before = set(keys.used)
        assert adapter.answer_requirement_error(result, 'overview') is None
        assert keys.used == before


def test_defaults_match_and_missing_top_value_is_usage(project, monkeypatch):
    monkeypatch.chdir(project)
    a, b = run('overview', '--format', 'json'), run('overview://', '--format', 'json')
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))
    invalid = run('overview', '--top')
    assert invalid.returncode == 2 and 'usage:' in invalid.stderr


@pytest.mark.parametrize('flag', ['--head', '--tail', '--max-items'])
def test_flat_list_budgets_do_not_silently_cut_nested_map(project, flag):
    result = run('overview://proj', flag, '1', '--format', 'json')
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body['map']['components']['returned'] == 5
    assert flag in result.stderr or any(w['type'] == 'unused_flag' for w in body.get('meta', {}).get('warnings', []))


def test_existing_static_sibling_hook_accepts_class_and_instance():
    from reveal.adapters.architecture import ArchitectureAdapter
    from reveal.cli.routing.declared import qualify_declared_answer
    from reveal.utils.results import ResultBuilder
    result = ResultBuilder.create('architecture_diff', '.', data={'analysis': {'complete': True}})
    assert qualify_declared_answer(result, ArchitectureAdapter, '.', 'architecture_diff') is result
    assert qualify_declared_answer(result, ArchitectureAdapter('.'), '.', 'architecture_diff') is result
