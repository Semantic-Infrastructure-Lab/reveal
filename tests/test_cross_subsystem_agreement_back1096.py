"""Oracle-free cross-subsystem agreement (BACK-1096, slice 2).

Two implementations answering the same question must agree; a disagreement
proves one is wrong without saying which.  Pairs from the consistency audit's
"Not assessed" list (REVEAL_CROSS_SUBSYSTEM_CONSISTENCY_AUDIT_2026-08-10.md).
"""
import re
from collections import Counter

import pytest

import reveal.analyzers  # noqa: F401  (registers every analyzer)
from reveal.adapters.stats import StatsAdapter
from reveal.cli.file_checker import check_and_collect_file
from reveal.registry import get_analyzer
from reveal.rules import RuleRegistry
from reveal.rules.maintainability.M101 import M101

pytestmark = [pytest.mark.component]


@pytest.fixture(autouse=True)
def serial_pools(monkeypatch):
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')


# ---------------------------------------------------------------- line counts

FILLER = ''.join('x%d = %d\n' % (i, i) for i in range(520))   # > M101's 500-line floor
TAIL = 'def tail():\n    return 1\n'
DISAGREE = ('FileAnalyzer._read_file uses str.splitlines() (it also splits on \\x0c, \\x85, \\u2028): '
            'stats://, M101 and ast:// all count one line too many')


def _spell(label):
    """(text, bom) for a 522-line file whose last line ends a function."""
    odd = {'formfeed': '\x0c\n', 'u2028': 's = "a b"\n', 'nel': 's = "a\x85b"\n'}
    text = FILLER + odd.get(label, '') + TAIL
    if label in ('crlf', 'bom_crlf'):
        text = text.replace('\n', '\r\n')
    if label == 'no_final_newline':
        text = text.rstrip('\n')
    return text, label.startswith('bom')


LINE_VARIANTS = [
    'lf', 'crlf', 'bom', 'bom_crlf', 'no_final_newline',
    pytest.param('formfeed', marks=pytest.mark.xfail(strict=True, reason=DISAGREE)),
    pytest.param('u2028', marks=pytest.mark.xfail(strict=True, reason=DISAGREE)),
    pytest.param('nel', marks=pytest.mark.xfail(strict=True, reason=DISAGREE)),
]


def _line_counts(tmp_path, label):
    text, bom = _spell(label)
    path = tmp_path / 'sample.py'
    path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8'))
    analyzer = get_analyzer(str(path))(str(path))
    last_function_end = analyzer.get_structure()['functions'][-1]['line_end']
    stats_total = StatsAdapter(str(path)).get_structure()['files'][0]['lines']['total']
    (detection,) = M101().check(str(path), None, analyzer.content)
    m101_total = int(re.search(r'([\d,]+) lines', detection.context).group(1).replace(',', ''))
    return last_function_end, stats_total, m101_total


@pytest.mark.parametrize('label', LINE_VARIANTS)
def test_stats_m101_and_ast_agree_on_line_count(tmp_path, label):
    text, _ = _spell(label)
    last_function_end, stats_total, m101_total = _line_counts(tmp_path, label)
    true_total = text.count('\n') + (0 if text.endswith('\n') else 1)
    assert stats_total == m101_total == last_function_end == true_total


def test_empty_file_has_zero_lines_in_every_counter(tmp_path):
    path = tmp_path / 'empty.py'
    path.write_text('', encoding='utf-8')
    assert StatsAdapter(str(path)).get_structure()['files'][0]['lines']['total'] == 0
    assert M101().check(str(path), None, '') == []


# ------------------------------------------------- check --select vs rule.check

KITCHEN_SINK = '''import os, sys
import os


def f(a, b=[], c={}):
    try:
        x = 1
    except:
        pass
    if a == None:
        print("hi")
    for i in range(10):
        for j in range(10):
            for k in range(10):
                if i and j or k:
                    while True:
                        if a:
                            return 1
    eval("1")
    return x  # TODO fix ''' + 'y' * 200 + '''


class A:
    pass
'''


def _key(detection):
    return (detection.rule_code, detection.line, detection.column, detection.message)


def test_select_one_rule_equals_calling_that_rule_directly(tmp_path):
    path = tmp_path / 'sink.py'
    path.write_text(KITCHEN_SINK, encoding='utf-8')
    RuleRegistry.discover()
    analyzer = get_analyzer(str(path))(str(path))
    structure, content = analyzer.get_structure(extract_links=True), analyzer.content
    fired, compared = set(), 0
    for rule_class in RuleRegistry.get_rules():
        if not rule_class.matches_target(str(path)):
            continue
        rule = RuleRegistry.get_configured_rule(rule_class.code, str(path))
        direct = [_key(d) for d in rule.check(str(path), structure, content) or []]
        _, routed, status = check_and_collect_file(path, tmp_path, [rule_class.code], None)
        assert status['status'] in ('ok', 'warning'), (rule_class.code, status)
        assert [_key(d) for d in routed] == direct, rule_class.code
        compared += 1
        if direct:
            fired.add(rule_class.code)
    assert compared >= 20 and len(fired) >= 5, 'positive control: rules must actually fire here'


def test_unselected_run_is_the_union_of_single_rule_runs(tmp_path):
    path = tmp_path / 'sink.py'
    path.write_text(KITCHEN_SINK, encoding='utf-8')
    RuleRegistry.discover()
    _, everything, _ = check_and_collect_file(path, tmp_path, None, None)
    union = Counter()
    for rule_class in RuleRegistry.get_rules():
        _, routed, _ = check_and_collect_file(path, tmp_path, [rule_class.code], None)
        union.update(_key(d) for d in routed)
        assert {d.rule_code for d in routed} <= {rule_class.code}, 'select leaked another rule'
    assert Counter(_key(d) for d in everything) == union
    assert len(union) >= 5


# ----------------------------------- adapter get_structure() vs get_element()
# Everything an overview lists must resolve by name, and the detail view must
# repeat the overview's numbers (a listed name that "is not found" is the
# BACK-530 failure class, here for URI adapters rather than file analyzers).

def test_json_every_listed_key_resolves_to_its_listed_value(tmp_path):
    from reveal.adapters.json import JsonAdapter
    path = tmp_path / 'keys.json'
    path.write_text('{"alpha": {"x": 1}, "a.b": 2, "c[0]": 3, "sp ace": 4, "": 5, '
                    '"nil": null, "caf\\u00e9": 6, "0": 7}\n', encoding='utf-8')
    adapter = JsonAdapter(str(path))
    listed = adapter.get_structure()['value']
    assert len(listed) == 8, 'positive control: awkward keys are listed'
    for key, value in listed.items():
        element = adapter.get_element(key)
        assert element is not None, key
        assert element['value'] == value, key


def _sqlite_fixture(tmp_path):
    import sqlite3
    path = tmp_path / 'agree.db'
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            'create table "we ird"(id integer primary key, name text);'
            'create index i1 on "we ird"(name);'
            'create table child(id integer, p integer references "we ird"(id));'
            'create table w(k text primary key) without rowid;'
            'insert into "we ird" values (1, "a"), (2, "b");'
            'create view v as select * from child;')
        conn.commit()
    finally:
        conn.close()
    return path


def test_sqlite_table_detail_repeats_the_overview_numbers(tmp_path):
    from reveal.adapters.sqlite import SQLiteAdapter
    adapter = SQLiteAdapter('sqlite://' + str(_sqlite_fixture(tmp_path)))
    overview = adapter.get_structure()
    tables = [t for t in overview['tables'] if t['type'] == 'table']
    assert {t['name'] for t in tables} == {'we ird', 'child', 'w'}
    for listed in tables:
        detail = adapter.get_element(listed['name'])
        assert detail is not None, listed['name']
        assert (detail['row_count'], len(detail['columns']), len(detail['indexes'])) == (
            listed['rows'], listed['columns'], listed['indexes']), listed['name']
    assert sum(len(adapter.get_element(t['name'])['foreign_keys']) for t in tables) == (
        overview['statistics']['foreign_keys'])
    assert sum(t['rows'] for t in tables) == overview['statistics']['total_rows']


@pytest.mark.xfail(strict=True, reason=(
    'sqlite:// lists views in get_structure()["tables"] but get_element() only looks '
    "up type='table', so a listed view is 'not found'"))
def test_sqlite_every_listed_object_resolves_by_name(tmp_path):
    from reveal.adapters.sqlite import SQLiteAdapter
    adapter = SQLiteAdapter('sqlite://' + str(_sqlite_fixture(tmp_path)))
    listed = adapter.get_structure()['tables']
    assert 'v' in {t['name'] for t in listed}, 'positive control: the view is listed'
    assert [t['name'] for t in listed if adapter.get_element(t['name']) is None] == []


def test_env_every_listed_variable_resolves_to_the_same_facts(monkeypatch):
    from reveal.adapters.env import EnvAdapter
    planted = {'REVEAL_B1096_PLAIN': 'value', 'REVEAL_B1096_API_KEY': 'hunter2-secret',
               'REVEAL_B1096_ACCENT': 'caf\u00e9'}
    for name, value in planted.items():
        monkeypatch.setenv(name, value)
    adapter = EnvAdapter()
    listed = {v['name']: (category, v)
              for category, variables in adapter.get_structure()['categories'].items()
              for v in variables}
    assert set(planted) <= set(listed), 'positive control: planted variables are listed'
    for name in planted:
        category, entry = listed[name]
        element = adapter.get_element(name)
        assert element is not None, name
        assert element['category'] == category, name
        for field in ('value', 'sensitive', 'length'):
            assert element[field] == entry[field], (name, field)
    assert listed['REVEAL_B1096_API_KEY'][1]['sensitive'] is True
    assert 'hunter2-secret' not in str(adapter.get_structure())


# ------------------------------------------- imports:// vs depends:// edges

def _python_project(root, files):
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="probe"\n', encoding='utf-8')
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    return root


def _import_edges(root):
    """{file: set(files that depend on it)} from the imports:// graph."""
    from reveal.adapters.imports import ImportsAdapter
    adapter = ImportsAdapter(resource=str(root))
    adapter._build_graph(root)
    dependents = {}
    for source, targets in adapter.analysis.graph.dependencies.items():
        for target in targets:
            dependents.setdefault(target.relative_to(root).as_posix(), set()).add(
                source.relative_to(root).as_posix())
    return adapter, dependents


def _depends_edges(root):
    from reveal.adapters.depends import DependsAdapter
    found = {}
    for path in sorted(root.rglob('*.py')):
        result = DependsAdapter(str(path)).get_structure()
        found[path.relative_to(root).as_posix()] = {d['file'] for d in result['dependents']}
    return found


SHAPES = {
    'absolute_and_relative': {
        'pkg/__init__.py': '', 'pkg/a.py': 'import os\nfrom . import b\n',
        'pkg/b.py': 'from .c import x\n', 'pkg/c.py': 'x = 1\n',
        'main.py': 'import pkg.a\nimport requests\n', 'tool.py': 'from pkg.b import x\nimport pkg.c as cc\n'},
}


@pytest.mark.parametrize('shape', SHAPES)
def test_imports_and_depends_agree_on_who_depends_on_whom(tmp_path, shape):
    root = _python_project(tmp_path / shape, SHAPES[shape])
    _, imports_edges = _import_edges(root)
    depends_edges = _depends_edges(root)
    assert sum(len(v) for v in depends_edges.values()) >= 5, 'positive control: edges exist'
    for name, dependents in depends_edges.items():
        assert imports_edges.get(name, set()) == dependents, name


MEMBER_IMPORT = {
    'pkg/__init__.py': '', 'pkg/a.py': 'from pkg import b\n', 'pkg/b.py': 'import pkg.a\n',
}
MEMBER_REASON = ("imports:// drops the file edge of an absolute `from pkg import submodule` "
                 '(depends:// keeps it), so a cycle made of such edges is invisible to ?circular')


@pytest.mark.xfail(strict=True, reason=MEMBER_REASON)
def test_member_import_of_a_submodule_is_a_file_edge_in_both(tmp_path):
    root = _python_project(tmp_path / 'member', {
        **MEMBER_IMPORT, 'main.py': 'from pkg import b\n'})
    _, imports_edges = _import_edges(root)
    depends_edges = _depends_edges(root)
    assert 'main.py' in depends_edges['pkg/b.py'], 'positive control: depends:// sees the edge'
    assert imports_edges.get('pkg/b.py', set()) == depends_edges['pkg/b.py']


@pytest.mark.xfail(strict=True, reason=MEMBER_REASON)
def test_cycle_through_a_member_import_is_found_by_imports(tmp_path):
    root = _python_project(tmp_path / 'cycle', MEMBER_IMPORT)
    depends_edges = _depends_edges(root)
    assert 'pkg/a.py' in depends_edges['pkg/b.py'] and 'pkg/b.py' in depends_edges['pkg/a.py'], (
        'positive control: depends:// sees a <-> b')
    adapter, _ = _import_edges(root)
    assert len(adapter.analysis.graph.find_cycle_groups()) == 1
