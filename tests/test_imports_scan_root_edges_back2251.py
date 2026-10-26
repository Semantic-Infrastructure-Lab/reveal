"""imports counts only edges whose target is under the scan root (BACK-2251).

``import '../assets/x.css'`` in ``src/a.ts`` resolves to a file above ``&root=proj/src``. The rule an
answer prints says it counts imports between files under the scan root and shows rows that are files
under the requested path, yet the edge was counted (a.ts fan-out 2) and the target given a row (fan-in 1).
Views filter edges, never drop them from the graph (REVEAL_PLAN W2): the scan-root view is the third beside
``lazy`` and ``tests``. The statement view keeps ``resolved: ../assets/x.css``, the fact stays visible.
"""
import json

from conftest import _run_reveal_in


def _project(tmp_path):
    proj = tmp_path / 'proj'
    (proj / 'src').mkdir(parents=True)
    (proj / 'assets').mkdir()
    (proj / 'package.json').write_text('{"name": "p"}\n', encoding='utf-8')
    (proj / 'assets' / 'x.css').write_text('a {}\n', encoding='utf-8')
    (proj / 'src' / 'a.ts').write_text("import '../assets/x.css';\nimport { b } from './b';\n", encoding='utf-8')
    (proj / 'src' / 'b.ts').write_text('export const b = 1;\n', encoding='utf-8')
    return proj


def _json(tmp_path, uri):
    result = _run_reveal_in(tmp_path, uri, '--format', 'json')
    assert result.returncode == 0, (uri, result.stderr)
    return json.loads(result.stdout)


def _text(tmp_path, uri):
    result = _run_reveal_in(tmp_path, uri)
    assert result.returncode == 0, (uri, result.stderr)
    return result.stdout


def _fan(data):
    return {e['file']: (e['fan_in'], e['fan_out']) for e in data['entries']}


def test_a_pinned_root_ranks_no_row_for_a_target_above_it(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?rank=fan-in&root=proj/src')
    assert _fan(data) == {'a.ts': (0, 1), 'b.ts': (1, 0)}


def test_scope_path_ranks_no_row_for_a_target_above_it(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?rank=fan-in&scope=path')
    assert _fan(data) == {'a.ts': (0, 1), 'b.ts': (1, 0)}


def test_fan_in_and_fan_out_totals_agree(tmp_path):
    _project(tmp_path)
    for uri in ('imports://proj/src?rank=fan-in&root=proj/src', 'imports://proj/src?rank=fan-in&scope=path'):
        entries = _json(tmp_path, uri)['entries']
        assert sum(e['fan_in'] for e in entries) == sum(e['fan_out'] for e in entries), uri


def test_the_rule_counts_the_edges_it_left_out(tmp_path):
    _project(tmp_path)
    rule = _json(tmp_path, 'imports://proj/src?rank=fan-in&root=proj/src')['edge_rule']
    assert rule['outside_root_edges'] == 1
    assert '1 edge(s) resolve outside the scan root, not counted' in rule['text']


def test_the_rule_is_silent_when_every_edge_is_inside(tmp_path):
    _project(tmp_path)
    rule = _json(tmp_path, 'imports://proj?rank=fan-in')['edge_rule']
    assert rule['outside_root_edges'] == 0
    assert 'outside the scan root' not in rule['text']


def test_the_statement_view_keeps_the_resolved_target(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?root=proj/src')
    assert {s['line']: s['resolved'] for s in data['files']['a.ts']} == {1: '../assets/x.css', 2: 'b.ts'}


def test_the_default_scope_answer_is_unchanged(tmp_path):
    """Control: the scan root is the project, the target is inside it, the row is hidden and the edge counted."""
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?rank=fan-in')
    assert _fan(data) == {'a.ts': (0, 2), 'b.ts': (1, 0)}
    assert 'outside the scan root' not in data['edge_rule']['text']


def test_importers_text_states_the_count(tmp_path):
    _project(tmp_path)
    out = _text(tmp_path, 'imports://proj/src?importers&root=proj/src')
    assert '../assets/x.css' not in out.split('Rule:')[0]
    assert 'resolve outside the scan root, not counted' in out
