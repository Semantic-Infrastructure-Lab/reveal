"""format=dot on a calls view that draws no graph exits 2 instead of printing text (BACK-2108).

``?callees=NAME`` at depth 1 is a per-definition call list (no edge resolution), and ``?rank=callers`` and
the retired ``?uncalled`` are tables: none has a dot renderer, and each accepted ``format=dot`` and printed
its text view with exit 0. The views that draw a graph (callers, a callees walk at depth 2-5 or with detail,
the retired root, the retired modules) are unchanged.
"""
import pytest

from conftest import _run_reveal_direct as run

pytestmark = pytest.mark.component

SOURCE = 'def a():\n    b()\n    c()\n\n\ndef b():\n    c()\n\n\ndef c():\n    pass\n'

# The depth-2 walk's dot, as master d8e21111 printed it: the negative control is byte-identical.
DEPTH_2_DOT = ('digraph calls {\n'
               '  rankdir=LR;\n'
               '  node [shape=box fontname="monospace"];\n'
               '  "a" [style=filled fillcolor=lightblue];\n'
               '  "a" -> "b";\n'
               '  "a" -> "c";\n'
               '  "b" -> "c";\n'
               '}\n')


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'm.py').write_text(SOURCE, encoding='utf-8')
    return tmp_path.as_posix()


@pytest.mark.parametrize('query', ['callees=a&format=dot', 'callees=a&depth=1&format=dot',
                                   'callees=m.py:a&format=dot', 'rank=callers&format=dot',
                                   'uncalled&format=dot'])
def test_dot_on_a_view_without_a_graph_exits_2_and_says_why(root, query):
    result = run(f'calls://{root}?{query}')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert 'format=dot' in result.stderr
    assert 'digraph' not in result.stdout
    # The text view is not printed in its place.
    for header in ('Callees of:', 'Most-called functions:', 'Dead code candidates:'):
        assert header not in result.stdout


def test_rejection_names_the_views_that_draw_a_graph(root):
    stderr = run(f'calls://{root}?callees=a&format=dot').stderr
    assert 'depth=2' in stderr and 'detail' in stderr


# Negative controls: the dot views and the depth-1 text/json views are unchanged.

def test_depth_2_walk_dot_is_byte_identical(root):
    result = run(f'calls://{root}?callees=a&depth=2&format=dot')
    assert result.returncode == 0 and result.stdout == DEPTH_2_DOT


@pytest.mark.parametrize('query', ['callees=a&detail&format=dot', 'callers=c&format=dot', 'root=a&format=dot',
                                   'modules&format=dot'])
def test_graph_views_still_render_dot(root, query):
    result = run(f'calls://{root}?{query}')
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.startswith('digraph ')


@pytest.mark.parametrize('query', ['callees=a', 'callees=a&format=json', 'callees=a&format=text',
                                   'rank=callers&format=json'])
def test_depth_1_text_and_json_still_answer(root, query):
    result = run(f'calls://{root}?{query}')
    assert result.returncode == 0, (result.stdout, result.stderr)
