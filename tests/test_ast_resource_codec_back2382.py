"""AST URI resources follow the shared existing-path-first codec."""

import json
import subprocess
import sys
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.api import query
from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.factory import _canonical_init


def source(path, name='alpha'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'def {name}():\n    return 1\n', encoding='utf-8')
    return path


def uri(path):
    return 'ast://' + quote(path.as_posix(), safe='/:')


@pytest.mark.parametrize('transport', ['cli', 'api', 'factory'])
@pytest.mark.parametrize('name', ['space dir', 'Unicode Ω', 'amp&dir', 'percent%dir', 'plus+dir', "single'quote"])
def test_encoded_resource_cli_api_factory_and_literal_control(tmp_path, name, transport):
    path = source(tmp_path / name / 'app.py')
    expected = query(f'ast://{path.as_posix()}?name=alpha')
    assert expected['total_results'] == 1
    encoded = uri(path) + '?name=alpha'
    if transport == 'factory':
        adapter = _canonical_init(AstAdapter, encoded.split('://', 1)[1])
        assert adapter.path == path.as_posix()
        assert adapter.get_structure() == expected
    elif transport == 'api':
        assert query(encoded) == expected
    else:
        command = run(encoded, '--format', 'json')
        assert command.returncode == 0, command.stderr
        assert json.loads(command.stdout) == expected


@pytest.mark.parametrize('scheme', ['ast', 'imports', 'metrics'])
def test_real_cli_and_declared_siblings_decode_the_same_resource(tmp_path, scheme):
    path = source(tmp_path / 'space Ω & % +' / 'app.py')
    encoded = uri(path).replace('ast://', scheme + '://', 1)
    result = subprocess.run([sys.executable, '-m', 'reveal', encoded, '--format', 'json'],
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    assert not json.loads(result.stdout).get('error')


@pytest.mark.skipif(sys.platform == 'win32', reason="Windows cannot represent '?' in filenames")
def test_encoded_question_mark_is_not_reparsed_as_query(tmp_path):
    path = source(tmp_path / 'question?name=wrong&percent%+.py')
    answer = query(uri(path) + '?name=alpha&limit=1')
    assert answer['path'] == path.as_posix()
    assert answer['total_results'] == 1
    command = run(uri(path) + '?name=alpha&limit=1', '--format', 'json')
    assert command.returncode == 0, command.stderr
    assert json.loads(command.stdout) == answer
    assert AstAdapter(path.as_posix(), 'name=alpha').get_structure() == answer


def test_literal_existing_percent_precedence_and_exactly_one_decode(tmp_path):
    literal = source(tmp_path / 'literal%20name.py', 'literal')
    source(tmp_path / 'literal name.py', 'decoded')
    raw_uri = 'ast://' + literal.as_posix()
    for spelling in (raw_uri, uri(literal)):
        assert query(spelling)['results'][0]['name'] == 'literal'
        command = run(spelling, '--format', 'json')
        assert command.returncode == 0, command.stderr
        assert json.loads(command.stdout)['results'][0]['name'] == 'literal'
    once = tmp_path / 'only%2520.py'
    source(tmp_path / 'only .py', 'too_far')
    assert _canonical_init(AstAdapter, once.as_posix()).path == once.as_posix()
    assert AstAdapter(quote(literal.as_posix(), safe='/:')).path == quote(literal.as_posix(), safe='/:')


@pytest.mark.parametrize('suffix', ['%FF', '%00'])
def test_invalid_resource_rejects_before_analysis(tmp_path, monkeypatch, suffix):
    def unexpected(self):
        pytest.fail('invalid URI reached source analysis')
    monkeypatch.setattr(AstAdapter, '_collect_structures', unexpected)
    encoded = f'ast://{tmp_path.as_posix()}/{suffix}'
    with pytest.raises(ValueError):
        query(encoded)
    command = run(encoded, '--format', 'json')
    assert command.returncode == 2, command.stderr
    assert json.loads(command.stdout)['error']


def test_projection_failure_and_mode_identity_survive_encoding(tmp_path):
    path = source(tmp_path / 'space name' / 'app.py')
    path.with_name('broken.py').write_text('def broken(:\n', encoding='utf-8')
    command = run(uri(path.parent), '--format', 'json', '--fields', 'results')
    assert command.returncode == 3, command.stderr
    assert json.loads(command.stdout)['results']
    missing = uri(path.parent / 'missing') + '?show=dict-heatmap'
    failed = run(missing, '--format', 'json')
    assert failed.returncode == 2
    assert json.loads(failed.stdout)['type'] == 'ast_dict_heatmap'


def test_api_kwargs_and_raw_query_codec_are_unchanged(tmp_path):
    path = source(tmp_path / 'space name.py')
    encoded = uri(path) + '?limit=1'
    assert query(encoded, limit=0) == query(encoded)
    with pytest.raises(ValueError, match='limit'):
        query(uri(path) + '?limit=bad', limit=0)
    assert query(uri(path) + '?name=alpha%26beta')['results'] == []


def test_resource_schema_declares_existing_path_first():
    assert AstAdapter.get_schema()['resource']['uri_codec'] == 'existing-path-first'
