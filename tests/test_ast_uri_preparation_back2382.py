"""URI preparation failures preserve legacy answers and clear request scope."""

import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.api import query
from reveal.cli.defaults import _default_args
from reveal.cli.routing.uri import handle_uri, resolve_uri
from reveal.utils import exclusions, gitignore, query_binding


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project space'
    root.mkdir()
    for name in ('keep', 'omit'):
        (root / (name + '.py')).write_text(f'def {name}():\n    return 1\n', encoding='utf-8')
    exclusions.clear_active_exclusions()
    yield root
    exclusions.clear_active_exclusions()


def encoded(root):
    return 'ast://' + quote(root.as_posix(), safe='/:')


def denied_codec(monkeypatch, path):
    original = query_binding._resource_exists
    def exists(value):
        if value == path:
            raise PermissionError('RESOURCE_CODEC_DENIED')
        return original(value)
    monkeypatch.setattr(query_binding, '_resource_exists', exists)


@pytest.mark.parametrize('mode', ['element', 'stdin', 'batch', 'check'])
@pytest.mark.parametrize('failure', ['%FF', '%00', 'permission'])
def test_unqualified_preparation_returns_legacy_failed_answer(project, monkeypatch, mode, failure):
    resource = encoded(project) + '/' + failure
    if failure == 'permission':
        denied_codec(monkeypatch, resource.split('://', 1)[1])
    args = _default_args(format='json', **({mode: True} if mode != 'element' else {}))
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err), pytest.raises(SystemExit) as stopped:
        if mode == 'element':
            handle_uri(resource, 'keep', args)
        else:
            answer = resolve_uri(resource, args)
            assert answer.execution_facts is None
            assert answer.kind == 'router'
            answer.emit()
    assert stopped.value.code == 1
    answer = json.loads(out.getvalue())
    assert answer['error']
    assert answer['type'] == 'ast'
    assert 'Traceback' not in err.getvalue()


@pytest.mark.parametrize('mode', ['element', 'stdin'])
@pytest.mark.parametrize('failure', ['%FF', '%00'])
def test_real_cli_unqualified_preparation_is_structured_failure(project, mode, failure):
    resource = encoded(project) + '/' + failure
    options = [resource, 'keep'] if mode == 'element' else ['--stdin']
    result = subprocess.run(
        [sys.executable, '-m', 'reveal', *options, '--format', 'json'],
        input=resource + '\n' if mode == 'stdin' else None,
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 1
    assert 'Traceback' not in result.stderr
    assert json.loads(result.stdout)['error']


@pytest.mark.parametrize('observation', ['scope', 'sibling'])
def test_exclusion_scope_is_cleared_when_later_preparation_fails(project, monkeypatch, observation):
    original = gitignore.split_respect_gitignore
    def split(resource):
        if 'respect_gitignore=invalid' in resource:
            assert exclusions.active_exclusions() == (project, ('omit.py',))
            raise ValueError('induced respect_gitignore preparation failure')
        return original(resource)
    # The existing bool parser accepts 'invalid'; inject failure after publication
    # to qualify cleanup at this boundary without changing query grammar.
    monkeypatch.setattr(gitignore, 'split_respect_gitignore', split)
    failed = resolve_uri(encoded(project) + '?respect_gitignore=invalid',
                         _default_args(format='json', exclude=['omit.py']))
    assert 'respect_gitignore' in failed.result['error']
    if observation == 'scope':
        assert exclusions.active_exclusions() == (None, ())
    else:
        answer = query('ast://' + project.as_posix())
        assert {row['name'] for row in answer['results']} == {'keep', 'omit'}


@pytest.mark.parametrize('leading_home', ['~', '%7E'])
def test_encoded_home_uses_expanded_path_for_preflight_and_exclusions(tmp_path, monkeypatch, leading_home):
    home = tmp_path / 'controlled home'
    project = home / 'project space'
    project.mkdir(parents=True)
    for name in ('keep', 'omit'):
        (project / (name + '.py')).write_text(f'def {name}():\n    return 1\n', encoding='utf-8')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    response = run('ast://' + leading_home + '/project%20space',
                   '--exclude', 'omit.py', '--format', 'json')
    assert response.returncode == 0, response.stderr
    answer = json.loads(response.stdout)
    assert answer['path'] == project.as_posix()
    assert {row['name'] for row in answer['results']} == {'keep'}
