"""Shared writes require lexical evidence, including genuine local shadows."""
from pathlib import Path

import pytest
import tree_sitter_language_pack as ts

from reveal.adapters.ast.nav_statewrites import collect_statewrites
from reveal.core.treesitter_compat import _zero_arg, tree_root, ts_parse
from reveal.rules.base_mixins import kind_nodes

pytestmark = pytest.mark.component
FIXTURES = Path(__file__).parent / 'fixtures' / 'statewrites_back1898'


def _scope(language, name):
    suffix = {'python': 'py', 'javascript': 'js', 'php': 'php'}[language]
    source = (FIXTURES / f'shared.{suffix}').read_text(encoding='utf-8')
    content = source.encode('utf-8')
    tree = ts_parse(ts.get_parser(language), source)
    root = tree_root(tree)
    assert not _zero_arg(root, 'has_error'), 'fixture must parse cleanly'
    if language == 'python':
        compile(source, 'shared.py', 'exec')

    def text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    funcs = kind_nodes(root, 'function_definition', 'function_declaration', 'method_declaration')
    func = next(node for node in funcs if text(node.child_by_field_name('name')) == name)
    return tree, func, text, source


def _writes(language, name):
    tree, func, text, source = _scope(language, name)
    start = _zero_arg(func, 'start_position').row + 1
    end = _zero_arg(func, 'end_position').row + 1
    first = collect_statewrites(func, start, end, text, language)
    assert collect_statewrites(func, start, end, text, language) == first
    # A fresh tree gives the same answer as repeated calls on the same tree.
    other_tree, other_func, other_text, _ = _scope(language, name)
    assert collect_statewrites(other_func, start, end, other_text, language) == first
    return first, source


def _expected(source, rows):
    lines = source.split('\n')
    return [dict(kind=kind, line=next(i for i, line in enumerate(lines, 1) if statement in line),
                 target=target, via='assignment') for kind, statement, target in rows]


@pytest.mark.parametrize(('language', 'rows'), [
    ('python', [('global', 'state[key] = 1', 'state[key]'),
                ('global', 'count = 3', 'count'), ('global', 'created = 4', 'created')]),
    ('javascript', [('global', 'state[key] = 1', 'state[key]'),
                    ('global', 'count = 3', 'count'), ('global', 'state[key] = 7', 'state[key]')]),
    ('php', [('global', '$state[$key] = 1', '$state[$key]'),
             ('global', '$created = 3', '$created'), ('global', "$GLOBALS['counter'] = 4", "$GLOBALS['counter']")]),
])
def test_module_mutations_and_explicit_global_rebindings(language, rows):
    writes, source = _writes(language, 'mutate')
    assert writes == _expected(source, rows)


@pytest.mark.parametrize(('language', 'name'), [
    ('python', 'parameter'), ('python', 'rebound'),
    ('javascript', 'parameter'), ('javascript', 'destructured'), ('javascript', 'rebound'),
    ('php', 'parameter'), ('php', 'bare'),
])
def test_genuine_local_bindings_are_not_shared_writes(language, name):
    assert _writes(language, name)[0] == []


@pytest.mark.parametrize('language', ['python', 'javascript'])
def test_nested_parameter_does_not_shadow_outer_scope(language):
    writes, source = _writes(language, 'nested')
    assert writes == _expected(source, [('global', 'state[key] = 3', 'state[key]')])


def test_python_class_scope_and_existing_field_env_siblings():
    writes, source = _writes('python', 'update')
    assert writes == _expected(source, [
        ('global', 'state[key] = 4', 'state[key]'),
        ('field', 'self.field = 1', 'self.field'),
        ('env', "os.environ['REVEAL_TEST_STATE'] = '1'", "os.environ['REVEAL_TEST_STATE']"),
    ])


def test_python_nonlocal_mutation_and_rebinding():
    writes, source = _writes('python', 'closure')
    assert writes == _expected(source, [('nonlocal', 'cell[key] = 2', 'cell[key]'),
                                       ('nonlocal', '        cell = {}', 'cell')])


@pytest.mark.parametrize(('language', 'rows'), [
    ('javascript', [('field', 'this.field = 1', 'this.field'),
                    ('env', "process.env.REVEAL_TEST_STATE = '1'", 'process.env.REVEAL_TEST_STATE')]),
    ('php', [('field', '$obj->field = 1', '$obj->field'),
             ('session', "$_SESSION['id'] = 2", "$_SESSION['id']")]),
])
def test_unchanged_field_environment_session_siblings(language, rows):
    writes, source = _writes(language, 'sibling')
    assert writes == _expected(source, rows)


def test_javascript_var_in_block_is_function_local():
    assert _writes('javascript', 'hoisted')[0] == []


def test_python_class_attribute_does_not_shadow_method_builtin():
    from reveal.adapters.ast.nav_bindings import BindingScope
    tree, func, text, source = _scope('python', 'builtin_method')
    assert not BindingScope(func, text, 'python').has_explicit_binding('print')


def test_implicit_closure_container_is_currently_declined():
    # Only explicit nonlocal storage is classified in this bounded slice.
    assert _writes('python', 'implicit_capture')[0] == []


@pytest.mark.parametrize('capture', ['$state', '&$state'])
def test_php_capture_reference_analysis_is_currently_declined(capture):
    source = f'<?php $state=[]; $f=function () use ({capture}) {{ $state[1]=2; }};'
    tree = ts_parse(ts.get_parser('php'), source)
    root = tree_root(tree)
    assert not _zero_arg(root, 'has_error')
    func, = kind_nodes(root, 'anonymous_function')
    content = source.encode('utf-8')
    text = lambda node: content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')
    assert collect_statewrites(func, 1, 1, text, 'php') == []
