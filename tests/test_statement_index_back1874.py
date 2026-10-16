"""BACK-1874: one statement-level index per tree replaces the per-rule re-walks.

`statement_index` must hand back exactly the statement-level slice of what `ast.walk` and a
full parent map would: same nodes, same order, same parents. B005, B006, B007, D005 and the
TypedDict collector then read it instead of walking the tree again; each is compared with
the walk it replaced, on input where the rule fires (a rule that reports nothing agrees
with anything).
"""

import ast
import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.analyzers._python_dict_usage import collect_typeddict_definitions
from reveal.rules.bugs.B005 import B005
from reveal.rules.bugs.B006 import B006
from reveal.rules.base_mixins import _cached_ast_parse
from reveal.rules.bugs.B007 import B007
from reveal.rules.duplicates.D005 import D005
from reveal.utils.pyparse import parse_python, statement_index

_STATEMENT_LIKE = (ast.stmt, ast.excepthandler, ast.match_case)

SOURCE = textwrap.dedent('''
    import os
    from .nope_one import missing_one
    try:
        from .nope_two import optional_two
        if os.name:
            import nope_three_optional
    except ImportError:
        from .nope_four import in_handler
    else:
        from .nope_five import in_else
    try:
        from .nope_six import caught_wrong_error
    except ValueError:
        pass

    SKIP_ONE = {'.git', 'node_modules', 'venv', '__pycache__', 'dist'}
    SKIP_TWO = ('.git', 'node_modules', 'venv', '__pycache__', 'dist')

    class Rec(TypedDict):
        name: str
        line: int

    class OverviewAdapter(ResourceAdapter):
        def run(self):
            try:
                os.getcwd()
            except Exception as e:
                logger.warning("failed %s", e)

    def helper(adapter: ResourceAdapter):
        try:
            os.getcwd()
        except Exception:
            logger.error("x")
        def inner():
            try:
                os.getcwd()
            except Exception:
                logger.error("z")
        key = lambda value: [v for v in value if v]
        return key

    def plain():
        try:
            os.getcwd()
        except Exception:
            pass

    def dispatch(command):
        match command:
            case "go":
                try:
                    os.getcwd()
                except OSError:
                    pass
            case _:
                import nope_seven_in_case
''')


def _tree():
    return parse_python(SOURCE, 'fixture.py')


def _full_parent_map(tree):
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _agreement_problems(tree, nodes, parents):
    """Differences between an index and the statement-level slice of the full walk."""
    expected_nodes = [n for n in ast.walk(tree) if n is not tree and isinstance(n, _STATEMENT_LIKE)]
    full = _full_parent_map(tree)
    expected_parents = {c: p for c, p in full.items() if isinstance(c, _STATEMENT_LIKE)}
    problems = []
    if [id(n) for n in nodes] != [id(n) for n in expected_nodes]:
        problems.append('nodes differ from the statement-level ast.walk order')
    if parents != expected_parents:
        problems.append('parents differ from the full parent map')
    return problems


def test_index_is_the_statement_level_slice_of_ast_walk_and_the_parent_map():
    tree = _tree()
    nodes, parents = statement_index(tree)
    assert any(isinstance(n, ast.ExceptHandler) for n in nodes)  # positive control
    assert any(isinstance(n, ast.match_case) for n in nodes)
    assert not any(isinstance(n, ast.expr) for n in nodes) and not any(
        isinstance(k, ast.expr) for k in parents)
    assert _agreement_problems(tree, nodes, parents) == []


def test_the_index_is_built_once_per_tree():
    tree = _tree()
    assert statement_index(tree) is statement_index(tree)


def test_agreement_check_notices_an_index_that_drops_a_node_kind():
    """Negative control: leaving out `except` clauses must be reported."""
    tree = _tree()
    nodes, parents = statement_index(tree)
    no_handlers = [n for n in nodes if not isinstance(n, ast.ExceptHandler)]
    assert _agreement_problems(tree, no_handlers, parents)
    reordered = list(reversed(nodes))
    assert _agreement_problems(tree, reordered, parents)


def test_index_agrees_on_the_reveal_package_itself():
    root = Path(reveal.__file__).parent
    checked = 0
    for path in sorted(root.rglob('*.py'))[:150]:
        tree = parse_python(path.read_text(encoding='utf-8'), str(path))
        nodes, parents = statement_index(tree)
        assert _agreement_problems(tree, nodes, parents) == [], path
        checked += 1
    assert checked > 50


def _legacy_optional_import_lines(tree):
    def catches(handler):
        if handler.type is None:
            return True
        if isinstance(handler.type, ast.Name):
            return handler.type.id in ('ImportError', 'ModuleNotFoundError')
        if isinstance(handler.type, ast.Tuple):
            return any(isinstance(el, ast.Name) and el.id in ('ImportError', 'ModuleNotFoundError')
                       for el in handler.type.elts)
        return False

    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(catches(h) for h in node.handlers):
            for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    lines.add(child.lineno)
    return lines


def test_b005_optional_import_lines_match_the_walk_it_replaced(tmp_path):
    tree = _tree()
    expected = _legacy_optional_import_lines(tree)
    assert len(expected) == 2  # body of the ImportError try, nested if included; handler/else/other try not
    assert B005()._find_optional_import_lines(tree) == expected
    path = tmp_path / 'fixture.py'
    path.write_text(SOURCE, encoding='utf-8')
    flagged = sorted(d.line for d in B005().check(str(path), None, SOURCE))
    assert flagged, 'B005 reports the dead imports outside optional blocks'
    assert not set(flagged) & expected


def _legacy_b007(rule, path, content):
    tree = parse_python(content, path)
    parent_map = _full_parent_map(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if rule._adapter_param_name(node, parent_map) is None:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.ExceptHandler) and rule._nearest_enclosing_function(
                    sub, parent_map) is node:
                detection = rule._check_handler(sub, path, content)
                if detection:
                    found.append(detection)
    return found


def test_b007_matches_the_walk_it_replaced():
    expected = _legacy_b007(B007(), 'fixture.py', SOURCE)
    assert len(expected) == 2  # method handler and helper handler; inner() and plain() are not adapter scopes
    got = B007().check('fixture.py', None, SOURCE)
    assert [(d.line, d.message) for d in got] == [(d.line, d.message) for d in expected]


def test_b006_matches_the_full_parent_map_it_replaced(monkeypatch):
    rule = B006()
    got = rule.check('fixture.py', None, SOURCE)
    assert got, 'B006 reports the silent handlers'
    seen = {}
    original = B006._check_handler

    def spy(self, node, file_path, content, lines, parent_map=None):
        seen['parent_map'] = parent_map
        return original(self, node, file_path, content, lines, parent_map)

    monkeypatch.setattr(B006, '_check_handler', spy)
    assert [d.line for d in B006().check('fixture.py', None, SOURCE)] == [d.line for d in got]
    tree = _cached_ast_parse(SOURCE, 'fixture.py')  # the tree the rule just received
    assert seen['parent_map'] is statement_index(tree)[1]
    full = _full_parent_map(tree)
    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
    assert handlers
    for handler in handlers:  # every handler climbs the same ancestors through either map
        via_full, via_index = full.get(handler), seen['parent_map'].get(handler)
        while via_full is not None:
            assert via_index is via_full
            via_full, via_index = full.get(via_full), seen['parent_map'].get(via_index)
        assert via_index is None


def test_d005_literals_match_the_walk_it_replaced():
    tree = _tree()
    got = D005()._literals_from_tree(tree)
    assert len(got) == 1  # SKIP_ONE; SKIP_TWO has the same canonical key and is deduplicated
    expected_lines = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assign)
                      and isinstance(n.value, (ast.Set, ast.Tuple, ast.List))]
    assert got[0][1] == min(expected_lines)


def test_typeddict_collector_matches_the_walk_it_replaced():
    tree = _tree()
    raw = {}
    collect_typeddict_definitions(tree, 'fixture.py', raw)
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert classes == {'Rec', 'OverviewAdapter'}
    assert set(raw) == classes
    assert raw['Rec'][0]['own_fields'] == ['name', 'line']
