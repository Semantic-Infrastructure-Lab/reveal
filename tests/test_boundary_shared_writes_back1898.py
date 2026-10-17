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
