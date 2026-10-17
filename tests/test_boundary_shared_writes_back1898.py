"""Boundary EFFECTS includes assignment writes without duplicate env reads."""
import pytest

from reveal.adapters.ast.nav_boundary import collect_boundary, render_boundary
from reveal.core.treesitter_compat import _zero_arg
from test_statewrites_globals_back1898 import _expected, _scope

pytestmark = pytest.mark.component


def _effects(language, name):
    tree, func, text, source = _scope(language, name)
    start = _zero_arg(func, 'start_position').row + 1
    end = _zero_arg(func, 'end_position').row + 1
    result = collect_boundary(func, start, end, text, language)
    assert collect_boundary(func, start, end, text, language) == result
    return result, source, render_boundary(result, start, end)


def _assignment_effects(source, rows):
    return [dict(kind=row['kind'], line=row['line'], callee=row['target'],
                 first_arg=None, has_more_args=False, via='assignment')
            for row in _expected(source, rows)]


@pytest.mark.parametrize(('language', 'rows'), [
    ('python', [('global', 'state[key] = 1', 'state[key]'),
                ('global', 'count = 3', 'count'), ('global', 'created = 4', 'created')]),
    ('javascript', [('global', 'state[key] = 1', 'state[key]'),
                    ('global', 'count = 3', 'count'), ('global', 'state[key] = 7', 'state[key]')]),
    ('php', [('global', '$state[$key] = 1', '$state[$key]'),
             ('global', '$created = 3', '$created'), ('global', "$GLOBALS['counter'] = 4", "$GLOBALS['counter']")]),
])
def test_boundary_exact_shared_assignment_effects(language, rows):
    result, source, rendered = _effects(language, 'mutate')
    assert result['effects'] == _assignment_effects(source, rows)
    assert 'state[key]()' not in rendered
    assert "GLOBALS['counter']()" not in rendered


def test_boundary_env_assignment_replaces_same_property_read_once():
    result, source, rendered = _effects('python', 'update')
    assert result['effects'] == _assignment_effects(source, [
        ('global', 'state[key] = 4', 'state[key]'),
        ('field', 'self.field = 1', 'self.field'),
        ('env', "os.environ['REVEAL_TEST_STATE'] = '1'", "os.environ['REVEAL_TEST_STATE']"),
    ])
    assert rendered.count("os.environ['REVEAL_TEST_STATE']") == 1
    assert 'self.field()' not in rendered


def test_boundary_explicit_nonlocal_effects():
    result, source, rendered = _effects('python', 'closure')
    assert result['effects'] == _assignment_effects(source, [
        ('nonlocal', 'cell[key] = 2', 'cell[key]'), ('nonlocal', '        cell = {}', 'cell')])
    assert 'cell[key]()' not in rendered


@pytest.mark.parametrize('language', ['python', 'javascript', 'php'])
def test_boundary_local_container_control(language):
    assert _effects(language, 'parameter')[0]['effects'] == []


@pytest.mark.parametrize(('language', 'source', 'target'), [
    ('python', "def root():\n    os.environ['X'] = os.environ['X'] + '1'\n", "os.environ['X']"),
    ('javascript', "function root() { process.env.X = process.env.X + '1'; }", 'process.env.X'),
])
def test_boundary_same_target_rhs_read_survives_assignment_merge(language, source, target):
    from test_binders_back1897 import parsed

    scope, text, end = parsed(language, source)
    result = collect_boundary(scope, 1, end, text, language)
    effects = [e for e in result['effects'] if e['callee'] == target]
    assert sorted(e['via'] for e in effects) == ['assignment', 'property']


def test_transitive_boundary_discloses_root_only_assignments(tmp_path):
    import json
    from conftest import _run_reveal_direct

    path = tmp_path / 'shared.py'
    path.write_text('''state = {}
def root(key):
    state[key] = 1
    helper(key)
def helper(key):
    state[key] = 2
    import logging
    logging.info(key)
''', encoding='utf-8')
    data = json.loads(_run_reveal_direct(str(path), 'root', '--boundary', '--transitive',
                                       '--format', 'json').stdout)
    assignments = [f for f in data['findings'] if f.get('via') == 'assignment']
    assert [(f['kind'], f['line'], f['callee'], f['hop'], f['chain']) for f in assignments] == [
        ('global', 3, 'state[key]', 0, ['root'])]
    assert any(f['kind'] == 'log' and f['hop'] == 1 for f in data['findings'])
    assert any('assignments only in the entry function' in w for w in data['warnings'])
    rendered = _run_reveal_direct(str(path), 'root', '--boundary', '--transitive').stdout
    assert 'assignments only in the entry function' in rendered
    assert 'state[key]()' not in rendered
