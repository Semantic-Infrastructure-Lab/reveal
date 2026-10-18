"""Actual implementation-only Contracts rows remain visible with zero declared contracts."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.contracts import ContractsAdapter
from reveal.mcp_server import reveal_query
from reveal.rendering.adapters.contracts import ContractsRenderer


@pytest.fixture(params=['flat', 'mixed'])
def implementation_tree(tmp_path, request):
    (tmp_path / 'visible.rs').write_text(
        'struct First;\nimpl External for First { fn go(&self) {} }\n'
        'struct Second;\nimpl External for Second { fn go(&self) {} }\n', encoding='utf-8')
    if request.param == 'mixed':
        (tmp_path / 'constant.py').write_text('VALUE = 1\n', encoding='utf-8')
    return tmp_path


def rust_group(result):
    return result.get('by_language', {}).get('rust', result)


@pytest.mark.parametrize('entrypoint', ['adapter', 'command', 'uri', 'mcp'])
def test_real_external_trait_implementations_are_visible_without_changing_contract_count(implementation_tree, entrypoint):
    root = implementation_tree
    result = ContractsAdapter(str(root)).get_structure()
    assert result['total_contracts'] == 0
    assert rust_group(result)['protocols'] == []
    assert [row['name'] for row in rust_group(result)['dataclasses']] == ['First', 'Second']
    assert all(row['file'].endswith('visible.rs') and type(row['line']) is int and row['line'] > 0
               for row in rust_group(result)['dataclasses'])
    if entrypoint == 'adapter':
        text = ContractsRenderer.render_structure(result, 'text')
    elif entrypoint == 'mcp':
        text = reveal_query(f'contracts://{root.as_posix()}')
        assert type(text) is str
    else:
        args = ['contracts', str(root)] if entrypoint == 'command' else [f'contracts://{root.as_posix()}']
        response = _run_reveal_direct(*args)
        assert response.returncode == 0, response.stderr
        text = response.stdout
    assert 'Total contracts found: 0' in text
    assert 'Implementing Types (2):' in text
    assert 'First' in text and 'Second' in text
    assert 'No contracts or seams found.' not in text


@pytest.mark.parametrize('query', ['abstract_only=true', 'implementations=false'])
def test_requested_filters_retain_genuinely_empty_result(implementation_tree, query):
    result = ContractsAdapter(str(implementation_tree), query).get_structure()
    assert result['total_contracts'] == 0
    assert rust_group(result)['dataclasses'] == []
    response = _run_reveal_direct(f'contracts://{implementation_tree.as_posix()}?{query}')
    assert response.returncode == 0, response.stderr
    assert 'No contracts or seams found.' in response.stdout
    assert 'Implementing Types' not in response.stdout


@pytest.mark.parametrize('language,source', [('python', 'VALUE = 1\n'), ('lua', 'local value = 1\n')])
def test_clean_zero_and_unsupported_language_stay_complete(tmp_path, language, source):
    extension = 'py' if language == 'python' else 'lua'
    (tmp_path / f'constant.{extension}').write_text(source, encoding='utf-8')
    response = _run_reveal_direct('contracts', str(tmp_path))
    payload = _run_reveal_direct('contracts', str(tmp_path), '--format', 'json')
    result = json.loads(payload.stdout)
    assert response.returncode == payload.returncode == 0
    assert result['total_contracts'] == 0
    assert 'Implementing Types' not in response.stdout
    if language == 'python':
        assert 'No contracts or seams found.' in response.stdout
    else:
        assert result['coverage']['warning']
        assert result['coverage']['warning'] in response.stdout


@pytest.mark.parametrize('cap', [1, 0])
def test_real_trait_nested_implementation_caps_remain_presentation_only(tmp_path, cap):
    (tmp_path / 'visible.rs').write_text(
        'trait Local { fn go(&self); }\n'
        'struct First;\nimpl Local for First { fn go(&self) {} }\n'
        'struct Second;\nimpl Local for Second { fn go(&self) {} }\n', encoding='utf-8')
    result = ContractsAdapter(str(tmp_path), f'impls={cap}&abstract_only=true').get_structure()
    assert result['total_contracts'] == 1
    assert [row['name'] for row in result['protocols'][0]['implementations']] == ['First', 'Second']
    text = ContractsRenderer.render_structure(result, 'text')
    assert 'Traits (1):' in text
    assert 'First' in text
    assert ('Second' in text) is (cap == 0)
    assert ('and 1 more' in text) is (cap == 1)
