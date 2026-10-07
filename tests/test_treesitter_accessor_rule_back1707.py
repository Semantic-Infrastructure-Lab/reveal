"""BACK-1707: V040 (tree-sitter Node accessors that break on the language-pack 1.8.1 floor),
the V-series home of scripts/check_treesitter_accessors.py (BACK-1406, BACK-1700).

The parametrized cases are the script's own unit tests, unchanged: the rule must give the same
findings. Below them: the rule over a fake checkout (both noqa spellings, both trees, a file that
does not parse is disclosed, not skipped) and over this checkout.
"""
import ast
import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.adapters.reveal.operations import check
from reveal.rules.validation.V040 import V040, find_offenders

pytestmark = pytest.mark.component


def offenders(src):
    return find_offenders(src, ast.parse(src))


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A fake dev checkout the V-rules resolve through REVEAL_DEV_ROOT; returns a writer
    for <tree>/<name> (dedented)."""
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
    for sub in ('analyzers', 'rules'):
        (tmp_path / 'reveal' / sub).mkdir(parents=True)
    (tmp_path / 'tests').mkdir()
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(tmp_path / 'reveal'))

    def write(rel, source):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return path
    return write


def _run():
    rule = V040()
    return rule, rule.check('reveal://', None, '')


@pytest.mark.parametrize('src, expected', [
    # The BACK-1406 helper that went red on the language-pack 1.8.1 floor.
    ("data[node.start_byte:node.end_byte]", [(1, 'end_byte'), (1, 'start_byte')]),
    ("n = node.child_count", [(1, 'child_count')]),
    ("root.has_error", [(1, 'has_error')]),
    ("node.start_point.row", [(1, 'start_point')]),
    ("node.to_sexp()", [(1, 'to_sexp')]),
    ("x = (\n    node\n    .end_byte)", [(2, 'end_byte')]),
])
def test_flags_bare_reads(src, expected):
    assert offenders(src) == expected


@pytest.mark.parametrize('src', [
    "data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')]",
    "node.start_byte = 3",                                   # write, not a read
    "m.child_count.return_value = 2",                         # MagicMock standing in for the method
    "m.start_byte.side_effect = lambda: 1",
    "node.start_point  # noqa: ts-accessor (the seam)",
    "node.type",                                             # not a guarded accessor
    "obj.start_time",
])
def test_allows(src):
    assert offenders(src) == []


_TS = "from reveal.core.treesitter_compat import node_children\n"


@pytest.mark.parametrize('src, expected', [
    # The three wave-2 patterns that reached CI red on the 1.8.1 floor (28f675fd, BACK-1700).
    (_TS + "kind in F and node.field_name_for_child(index) in F", [(2, 'field_name_for_child')]),
    (_TS + "stack.extend(node.children)", [(2, 'children')]),
    (_TS + "if child == target_node:\n    pass", [(2, '==')]),
    (_TS + "node.field_name_for_named_child(0)", [(2, 'field_name_for_named_child')]),
    (_TS + "for c in tree_root(tree).children: pass", [(2, 'children')]),
    (_TS + "x = a_node != b_node", [(2, '==')]),
    (_TS + "a = node.child_by_field_name('x').children", [(2, 'children')]),
])
def test_flags_floor_hazards(src, expected):
    assert offenders(src) == expected


@pytest.mark.parametrize('src', [
    # Negative controls: the same spellings that are not tree-sitter nodes, or the safe form.
    "stack.extend(node.children)",                            # no tree-sitter in this file
    "x = child == other",
    _TS + "stack.extend(node_children(node))",
    _TS + "for c in el.children: pass",                      # reveal's Element model receiver
    _TS + "self.children",
    _TS + "if node == None: pass",
    _TS + "if node.type == 'identifier': pass",
    _TS + "if child == 'x': pass",
    _TS + "key = (_zero_arg(a, 'start_byte'), _zero_arg(a, 'end_byte')) == (1, 2)",
    _TS + "stack.extend(node.children)  # noqa: ts-accessor",
    _TS + "if node is target_node: pass",
])
def test_allows_safe_forms(src):
    assert offenders(src) == []


def test_attributes():
    rule = V040()
    assert (rule.code, rule.internal, rule.uri_patterns) == ('V040', True, ['^reveal://.*'])


def test_ignores_a_regular_file():
    assert V040().check('reveal/x.py', None, 'node.start_byte') == []


@pytest.mark.parametrize('rel, expected', [
    ('reveal/pkg/mod.py', [('reveal/pkg/mod.py', 2)]),
    ('tests/test_x.py', [('tests/test_x.py', 2)]),
    ('tests/helper.py', [('tests/helper.py', 2)]),          # every .py, not only test_*.py
    ('scripts/tool.py', []),                                # only reveal/ and tests/
])
def test_rule_scans_reveal_and_tests(checkout, rel, expected):
    checkout(rel, "def f(node):\n    return node.start_byte\n")
    _, found = _run()
    assert sorted((d.file_path, d.line) for d in found) == expected


@pytest.mark.parametrize('comment', ['# noqa: ts-accessor (the seam)', '# noqa: V040 reviewed'])
def test_both_noqa_spellings_exempt_any_line_of_the_expression(checkout, comment):
    checkout('reveal/a.py', f"def f(node):\n    return (\n        node\n        .end_byte  {comment}\n    )\n")
    assert _run()[1] == []


def test_detection_message_advice_and_posix_path(checkout):
    checkout('reveal/sub/a.py', "def f(node):\n    return node.start_byte\n")
    [d] = _run()[1]
    assert d.file_path == 'reveal/sub/a.py' and '\\' not in d.file_path
    assert d.message.startswith('bare .start_byte') and "_zero_arg(node, 'start_byte')" in d.suggestion
    assert d.context == 'return node.start_byte'


def test_unparseable_module_is_disclosed_not_skipped(checkout):
    checkout('reveal/broken.py', "def f(:\n")
    checkout('reveal/ok.py', "def f(node):\n    return node.start_byte\n")
    rule, found = _run()
    assert [d.file_path for d in found] == ['reveal/ok.py']
    assert any(o['status'] == 'unavailable' for o in rule.outcomes)


def test_installed_package_is_not_applicable(tmp_path, monkeypatch):
    root = tmp_path / 'site' / 'reveal'
    for sub in ('analyzers', 'rules'):
        (root / sub).mkdir(parents=True)
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    rule, found = _run()
    assert found == [] and [o['status'] for o in rule.outcomes] == ['skipped']


def test_reveal_own_source_is_clean(monkeypatch):
    """Strict, not baselined: the only bare reads are the seam's own, marked noqa
    (what CI's `reveal reveal:// --check` runs)."""
    root = Path(reveal.__file__).parent
    if not (root.parent / 'tests').is_dir():
        pytest.skip('installed package, no tests/')
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    result = check(select=['V040'])
    assert result['detections'] == []
    assert {e['rule']: e['status'] for e in result['coverage']['rules']} == {'V040': 'run'}
