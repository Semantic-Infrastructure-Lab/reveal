"""BACK-2613 S5: what ast itself prints teaches the subcommand, never an ast:// query string (D20, ruling Q8).

Covered producers: ``help://ast`` (text and JSON), ``help://schemas/ast`` (``uri_syntax``, ``example_queries``, notes; B11
``cli_flags`` and ``output_types``; ``filter_fields`` without retired fields), the next steps of the dict views, the
reveal-type answer, the name-search and filter-correction hints, the W-CAP-1 text of the Python-only answers, and the
positional-element refusal (B13/B14). A URI may still name the resource (``ast://PATH --where ...``); what it may not do
is carry the options as a query string.
"""
import json
import re

import pytest

from conftest import _run_reveal_in

# An ast:// URI that carries a query string: ``ast://src?complexity>10``, ``ast://?show=...``.
AST_QUERY_STRING = re.compile(r"ast://[^\s'\"`]*\?[A-Za-z_]")

A_PY = '''def alpha(rows):
    for row in rows:
        print(row['a'], row['b'], row['c'])

def beta(rows):
    for row in rows:
        print(row['a'], row['b'], row['c'])

LIMIT = 3
'''


@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'a.py').write_text(A_PY, encoding='utf-8')
    (pkg / 'c.dart').write_text('int add(int a, int b) {\n  return a + b;\n}\n', encoding='utf-8')
    return tmp_path


def run(tree, *argv):
    result = _run_reveal_in(tree, *argv)
    return result.returncode, result.stdout, result.stderr


def query_strings(text):
    return AST_QUERY_STRING.findall(text)


@pytest.mark.parametrize('argv', [('help://ast',), ('help://ast', '--format', 'json'),
                                  ('help://schemas/ast',), ('help://schemas/ast', '--format', 'json')])
def test_help_pages_teach_no_ast_query_string(tree, argv):
    code, out, _ = run(tree, *argv)
    assert code == 0
    found = [line for line in out.splitlines() if query_strings(line)]
    assert not found, found


def test_schema_examples_are_subcommands_with_flags(tree):
    # The subcommand, as the ast:// request's own note names it (BACK-2769: the URI form retires too, D20).
    code, out, _ = run(tree, 'help://schemas/ast', '--format', 'json')
    schema = json.loads(out)
    assert '?' not in schema['uri_syntax'] and schema['uri_syntax'].startswith('reveal ast '), schema['uri_syntax']
    uris = [example['uri'] for example in schema['example_queries']]
    assert uris and all(uri.startswith('reveal ast ') and '?' not in uri for uri in uris), uris
    assert any('--view dict-heatmap' in uri for uri in uris), uris


def test_schema_b11_flags_types_and_fields(tree):
    code, out, _ = run(tree, 'help://schemas/ast', '--format', 'json')
    schema = json.loads(out)
    assert '--outline' not in schema['cli_flags'], schema['cli_flags']
    assert {'--where', '--kind', '--view', '--reveal-type'} <= set(schema['cli_flags']), schema['cli_flags']
    assert 'ast_reveal_type' in {t['type'] for t in schema['output_types']}
    assert not {'calls', 'callee_of', 'type', 'depth'} & set(schema['filter_fields']), sorted(schema['filter_fields'])
    assert {'kind', 'nesting_depth', 'complexity', 'name'} <= set(schema['filter_fields'])


@pytest.mark.parametrize('argv,expected', [
    (('ast', 'pkg', '--view', 'dict-heatmap'), 'reveal ast pkg --view dict-schemas'),
    (('ast', 'pkg', '--view', 'dict-schemas'), 'reveal ast pkg --view dict-heatmap'),
    (('ast', 'pkg', '--reveal-type', 'rows'), 'reveal ast pkg --where param_type=rows'),
    (('ast', 'pkg/a.py', '--where', 'name=LIMIT'), 'reveal ast pkg/a.py --reveal-type LIMIT'),
    (('ast', 'pkg', '--where', 'functions=1'), 'reveal ast PATH --kind function'),
])
def test_next_steps_teach_the_subcommand(tree, argv, expected):
    code, out, err = run(tree, *argv)
    assert not query_strings(out + err), out + err
    assert expected in out, out


@pytest.mark.parametrize('argv,invocation', [
    (('ast', 'pkg', '--view', 'dict-heatmap'), 'reveal ast --view dict-heatmap analyzes Python only'),
    (('ast', 'pkg', '--view', 'dict-schemas'), 'reveal ast --view dict-schemas analyzes Python only'),
    (('ast', 'pkg', '--reveal-type', 'rows'), 'reveal ast --reveal-type NAME analyzes Python only'),
])
def test_python_only_warning_names_the_subcommand(tree, argv, invocation):
    code, out, _ = run(tree, *argv, '--format', 'json')
    messages = [w['message'] for w in json.loads(out)['meta']['warnings'] if w.get('code') == 'W-CAP-1']
    assert messages and messages[0].startswith(invocation), messages


def test_positional_element_refusal_teaches_no_query_string(tree):
    code, out, err = run(tree, 'ast://pkg', 'alpha')
    assert code == 2
    assert "takes no positional element ('alpha')" in err
    assert not query_strings(err), err
    assert '--where' in err, err
