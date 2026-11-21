"""A retired field of a where expression notes its existing RETIREMENTS row on every transport (BACK-2613, ruling Q2).

COMMAND_MODEL "Retirement notes": any spelling with a row notes on CLI text, CLI JSON, ``api.query`` and MCP alike. A
where noun declares the fields whose spelling retired once, on its ``where_param`` (``retired_fields``); the declared
route and the Python URI path note ``param:<noun>.<field>`` for each such field a bound where term names, whether it was
typed as ``--where``, ``?where=`` or a bare ``?FIELD=VALUE``. It is data per noun, never an opt-in flag.
"""
import json

import pytest

from conftest import _run_reveal_in
from reveal.cli.invocation import RETIREMENTS, Invocation, Retirement, invocation_scope, noted_retirements


def test_where_param_carries_retired_fields():
    from reveal.utils.query_parser import where_param
    assert where_param('d', retired_fields=('old',)).retired_fields == ('old',)
    assert where_param('d').retired_fields == ()


def test_every_declared_retired_field_names_an_existing_row():
    from reveal.adapters.base import get_adapter_class, list_supported_schemes
    declared = {}
    for scheme in list_supported_schemes():
        for spec in getattr(get_adapter_class(scheme), 'PARAM_SPECS', None) or ():
            for field in getattr(spec, 'retired_fields', ()):
                declared[f'param:{scheme}.{field}'] = spec.name
    assert {'param:ast.calls', 'param:ast.callee_of'} <= set(declared)
    assert [key for key in declared if key not in RETIREMENTS] == []


@pytest.mark.parametrize('transport,query', [('typed', {'where': ['old=1', 'new>2']}), ('uri', 'where=old%3D1&new>2'),
                                             ('uri', 'old=1')])
def test_a_bound_term_on_a_retired_field_notes_its_row(monkeypatch, transport, query):
    from reveal.cli.routing.declared import note_retired_where_fields
    from reveal.utils.query_binding import prepare_declared_params
    from reveal.utils.query_parser import where_param
    spec = where_param('d', retired_fields=('old',), open_fields='any')
    monkeypatch.setitem(RETIREMENTS, 'param:demo.old', Retirement('demo ?old=', 'NEW', standalone=True))
    params = prepare_declared_params((spec,), query, transport)
    with invocation_scope(Invocation.parse(['reveal', 'demo', '.']), retirements_to_stderr=False):
        note_retired_where_fields('demo', (spec,), params, transport)
        assert list(noted_retirements()) == ['param:demo.old']


def test_a_term_on_another_field_notes_nothing(monkeypatch):
    from reveal.cli.routing.declared import note_retired_where_fields
    from reveal.utils.query_binding import prepare_declared_params
    from reveal.utils.query_parser import where_param
    spec = where_param('d', retired_fields=('old',), open_fields='any')
    monkeypatch.setitem(RETIREMENTS, 'param:demo.old', Retirement('demo ?old=', 'NEW', standalone=True))
    params = prepare_declared_params((spec,), {'where': ['older=1', 'new>2']}, 'typed')
    with invocation_scope(Invocation.parse(['reveal', 'demo', '.']), retirements_to_stderr=False):
        note_retired_where_fields('demo', (spec,), params, 'typed')
        assert noted_retirements() == {}


# --- ast, end to end on every transport ---------------------------------------------------------------------

@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'a.py').write_text('def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n', encoding='utf-8')
    return tmp_path


def _fields(document):
    return [w.get('field') for w in (document.get('meta') or {}).get('warnings') or []
            if w.get('code') == 'retired_spelling']


@pytest.mark.parametrize('argv', [
    ['ast', 'pkg', '--where', 'calls=alpha'], ['ast://pkg?where=calls=alpha'], ['ast://pkg', '--where', 'calls=alpha'],
    ['ast://pkg?calls=alpha&where=calls=alpha'],
])
def test_ast_cli_forms_note_the_row_once(tree, argv):
    result = _run_reveal_in(tree, *argv, '--format', 'json')
    document = json.loads(result.stdout)
    assert result.returncode == 0 and [r['name'] for r in document['results']] == ['beta']
    assert _fields(document).count('param:ast.calls') == 1, _fields(document)
    text = _run_reveal_in(tree, *argv)
    assert text.stderr.count('ast://?calls= is deprecated') == 1, text.stderr


def test_ast_python_and_mcp_note_the_row(tree):
    from reveal import api
    from reveal.mcp_server import reveal_run
    assert 'param:ast.calls' in _fields(api.query('ast', str(tree / 'pkg'), where=['calls=alpha']))
    assert 'param:ast.callee_of' in _fields(api.query(f'ast://{tree / "pkg"}', where=['callee_of=beta']))
    assert 'ast://?calls= is deprecated' in reveal_run(['ast', str(tree / 'pkg'), '--where', 'calls=alpha'])


@pytest.mark.parametrize('argv', [['ast', 'pkg', '--where', 'name=alpha'], ['markdown', 'pkg', '--where', 'calls=x']])
def test_other_fields_and_nouns_note_nothing(tree, argv):
    result = _run_reveal_in(tree, *argv, '--format', 'json')
    assert result.returncode == 0 and _fields(json.loads(result.stdout)) == []
