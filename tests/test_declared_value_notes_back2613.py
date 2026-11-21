"""A value row notes on the declared subcommand as on the URI (BACK-2613, ruling Q3).

RETIREMENTS keys a retired value ``value:<noun>.<param>=<value>`` (``ast://?show=calls``). The URI route derives those keys
from the query; the declared subcommand route derived only ``param:`` keys from the typed flags, so ``reveal ast P --show
calls`` answered the retired view with no note. The subcommand's retirement hook now looks up the value a flag carries
under the same key the URI spells, for every declared noun.
"""
import json

import pytest

from conftest import _run_reveal_in
from reveal.cli.invocation import RETIREMENTS, Retirement


@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'a.py').write_text('def alpha():\n    return 1\n\nclass Beta:\n    pass\n', encoding='utf-8')
    (tmp_path / 'rows.json').write_text(json.dumps([{'n': 1}]), encoding='utf-8')
    return tmp_path


def _fields(tree, *argv):
    result = _run_reveal_in(tree, *argv, '--format', 'json')
    document = json.loads(result.stdout)
    return result.returncode, [w.get('field') for w in (document.get('meta') or {}).get('warnings') or []
                               if w.get('code') == 'retired_spelling']


@pytest.mark.parametrize('argv,key', [
    (['--kind', 'class'], 'value:ast.kind=class'), (['--kind=class'], 'value:ast.kind=class'),
    (['--type', 'class'], 'value:ast.type=class'),  # an old flag spells its legacy word, as ?type=class does
])
def test_a_typed_value_notes_its_value_row(tree, monkeypatch, argv, key):
    monkeypatch.setitem(RETIREMENTS, key, Retirement('VALUE', 'NEW', standalone=True))
    code, fields = _fields(tree, 'ast', 'pkg', *argv)
    assert code == 0 and key in fields, fields


def test_another_value_notes_nothing(tree, monkeypatch):
    monkeypatch.setitem(RETIREMENTS, 'value:ast.kind=class', Retirement('VALUE', 'NEW', standalone=True))
    assert _fields(tree, 'ast', 'pkg', '--kind', 'function') == (0, [])


@pytest.mark.parametrize('argv', [['ast', 'pkg', '--show', 'calls'], ['ast://pkg', '--show', 'calls']])
def test_the_retired_calls_value_notes_on_the_subcommand(tree, argv):
    code, fields = _fields(tree, *argv)
    assert code == 0 and 'value:ast.show=calls' in fields, fields
    assert 'reveal calls' in _run_reveal_in(tree, *argv).stderr


def test_the_retired_calls_value_notes_on_python_and_mcp(tree):
    from reveal import api
    from reveal.mcp_server import reveal_run
    answer = api.query('ast', str(tree / 'pkg'), show='calls')
    assert 'value:ast.show=calls' in [w.get('field') for w in answer['meta']['warnings']]
    assert 'reveal calls' in reveal_run(['ast', str(tree / 'pkg'), '--show', 'calls'])


@pytest.mark.parametrize('argv', [
    ['ast', 'pkg', '--show', 'dict-heatmap'], ['json', 'rows.json', '--view', 'keys'],
    ['metrics', 'pkg', '--view', 'hotspots'], ['calls', 'pkg', '--sort=-callers'],
])
def test_values_without_a_row_note_nothing(tree, argv):
    code, fields = _fields(tree, *argv)
    assert code == 0 and [f for f in fields if f.startswith('value:')] == []


def test_every_value_row_names_a_declared_spelling():
    """A value row is reachable from the subcommand when its parameter is a declared spelling of the noun."""
    from reveal.adapters.base import get_adapter_class
    for key in (k for k in RETIREMENTS if k.startswith('value:')):
        noun, _, rest = key[len('value:'):].partition('.')
        param = rest.partition('=')[0]
        spellings = {s for spec in get_adapter_class(noun).PARAM_SPECS for s in spec.spellings}
        assert param in spellings, key
