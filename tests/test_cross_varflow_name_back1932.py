"""Resolved cross-varflow frames retain their function identity (BACK-1932)."""

import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav_cross_varflow import cross_var_flow
from reveal.registry import get_analyzer

pytestmark = pytest.mark.conformance

FIXTURES = Path(__file__).parent / 'fixtures' / 'conformance'


@pytest.mark.parametrize('language,extension,name,var', [
    ('zig', 'zig', 'processOrder', 'result'), ('zig', 'zig', 'run', 'order'),
    ('python', 'py', 'process_order', 'result'), ('lua', 'lua', 'processOrder', 'result'),
])
def test_cross_varflow_root_label_matches_resolved_entry(language, extension, name, var):
    path = str(FIXTURES / language / f'sample.{extension}')
    plain = _run_reveal_direct(path, name, '--varflow', var, '--format', 'json')
    crossed = _run_reveal_direct(path, name, '--varflow', var, '--cross-calls', '--format', 'json')
    assert plain.returncode == crossed.returncode == 0
    root = json.loads(crossed.stdout)['findings'][0]
    assert root['events'] == json.loads(plain.stdout)['findings']
    assert root['function'] == name


def test_lua_method_keeps_existing_qualified_field_label(tmp_path):
    path = tmp_path / 'method.lua'
    path.write_text('function Batch.run(value) return value end\n', encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    assert not analyzer.has_parse_errors()
    node = analyzer._find_nodes_by_type('function_declaration')[0]
    frames = cross_var_flow(analyzer, node, 'value', 1, 1, analyzer._get_node_text)
    assert frames[0]['function'] == 'Batch.run'
    assert [(event['kind'], event['line']) for event in frames[0]['events']] == [
        ('READ', 1), ('READ', 1),
    ]
