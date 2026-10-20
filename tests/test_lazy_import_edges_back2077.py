"""BACK-2077: the import graph keeps function-level (lazy) edges; only cycles leave them out.

``resolve_graph`` dropped every ``scope == 'local'`` import (BACK-445) so ``?circular``
reported no phantom cycles, which also took those importers out of fan-in. The graph now
keeps the edge with its scope; ``?circular`` (and ``metadata.has_cycles``) leave local
edges out by default, every other view counts them, and ``&lazy=include|exclude|only``
overrides both defaults. Every edge-derived answer prints the rule it counted by.

Fixture (Python, one directory): ``core`` is imported at module level by ``eager``, in a
function by ``lazy``, both ways by ``both`` and only under ``TYPE_CHECKING`` by ``typed``.
``ring_a -> ring_b`` is module level and ``ring_b -> ring_a`` lazy (BACK-445's shape);
``loop_a <-> loop_b`` is a module-level cycle; ``tc_a -> tc_b`` with a ``TYPE_CHECKING``
back-edge is never a cycle.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.imports import ImportsAdapter
from reveal.rules.imports.I002 import I002, _graph_cache
from reveal.utils.path_utils import to_posix

TC = 'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n'

FILES = {
    'core.py': 'X = 1\n',
    'eager.py': 'import core\n',
    'lazy.py': 'def f():\n    import core\n    return core.X\n',
    'both.py': 'import core\n\n\ndef f():\n    import core\n    return core.X\n',
    'typed.py': TC + '    import core\n',
    'ring_a.py': 'import ring_b\n',
    'ring_b.py': 'def f():\n    import ring_a\n    return ring_a\n',
    'loop_a.py': 'import loop_b\n',
    'loop_b.py': 'import loop_a\n',
    'tc_a.py': 'import tc_b\n',
    'tc_b.py': TC + '    import tc_a\n',
}

FAN_IN = {
    'include': {'core.py': 3, 'ring_a.py': 1, 'ring_b.py': 1, 'loop_a.py': 1, 'loop_b.py': 1, 'tc_b.py': 1},
    'exclude': {'core.py': 2, 'ring_b.py': 1, 'loop_a.py': 1, 'loop_b.py': 1, 'tc_b.py': 1},
    'only': {'core.py': 1, 'ring_a.py': 1},
}
FAN_OUT = {
    'include': {'eager.py': 1, 'lazy.py': 1, 'both.py': 1, 'ring_a.py': 1, 'ring_b.py': 1,
                'loop_a.py': 1, 'loop_b.py': 1, 'tc_a.py': 1},
    'exclude': {'eager.py': 1, 'both.py': 1, 'ring_a.py': 1, 'loop_a.py': 1, 'loop_b.py': 1, 'tc_a.py': 1},
    'only': {'lazy.py': 1, 'ring_b.py': 1},
}
CYCLES = {
    'include': [['loop_a.py', 'loop_b.py'], ['ring_a.py', 'ring_b.py']],
    'exclude': [['loop_a.py', 'loop_b.py']],
    'only': [],
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    _graph_cache.clear()
    yield
    _graph_cache.clear()


def _tree(root, files):
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var
    # A project marker keeps I002's scan root on the fixture (BACK-1723's fixtures do the same).
    for rel, text in {'pyproject.toml': '[project]\nname = "probe"\n', **files}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


@pytest.fixture
def project(tmp_path):
    return _tree(tmp_path / 'p', FILES)


def _run(uri, *extra):
    out = _run_reveal_direct(uri, *extra)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _json(uri):
    return json.loads(_run(uri, '--format', 'json'))


def _uri(root, query):
    return f'imports://{to_posix(root)}?{query}'


def _query(base, lazy):
    return base if lazy is None else f'{base}&lazy={lazy}'


def _ranks(data):
    entries = {to_posix(e['file']): e for e in data['entries']}
    fan_in = {f: e['fan_in'] for f, e in entries.items() if e['fan_in']}
    fan_out = {f: e['fan_out'] for f, e in entries.items() if e['fan_out']}
    return fan_in, fan_out


def _cycles(data):
    return sorted(sorted(to_posix(p) for p in group) for group in data['cycles'])


# ------------------------------------------------------------------ the &lazy matrix

@pytest.mark.parametrize('lazy', [None, 'include', 'exclude', 'only'])
def test_fan_in_by_lazy_mode(project, lazy):
    mode = lazy or 'include'  # fan-in's default counts every edge (the oracles' rule)
    data = _json(_uri(project, _query('rank=fan-in', lazy)))
    assert _ranks(data) == (FAN_IN[mode], FAN_OUT[mode])
    rule = data['edge_rule']
    assert rule['lazy'] == mode
    assert rule['lazy_default'] is (lazy is None)
    assert rule['type_checking'] == 'excluded'
    assert rule['tests'] == 'included'
    assert rule['unclassified_edges'] == 0


@pytest.mark.parametrize('lazy', [None, 'include', 'exclude', 'only'])
def test_cycles_by_lazy_mode(project, lazy):
    mode = lazy or 'exclude'  # ?circular's default leaves lazy edges out (BACK-445)
    data = _json(_uri(project, _query('circular', lazy)))
    assert _cycles(data) == CYCLES[mode]
    assert data['count'] == len(CYCLES[mode])
    assert data['edge_rule']['lazy'] == mode
    assert data['edge_rule']['lazy_default'] is (lazy is None)
    assert data['metadata']['has_cycles'] is bool(CYCLES[mode])
    assert data['metadata']['cycles_lazy'] == mode


def test_lazy_exclude_equals_the_circular_default(project):
    default = _json(_uri(project, 'circular'))
    explicit = _json(_uri(project, 'circular&lazy=exclude'))
    for key in ('cycles', 'cycle_paths', 'count'):
        assert default[key] == explicit[key]


def test_modes_partition_the_edges(project):
    """Oracle-free invariant: include = exclude + only, per file, for fan-in and fan-out."""
    by_mode = {m: _ranks(_json(_uri(project, f'rank=fan-in&lazy={m}'))) for m in FAN_IN}
    for which in (0, 1):
        files = set().union(*(by_mode[m][which] for m in by_mode))
        for f in files:
            assert by_mode['include'][which].get(f, 0) == (
                by_mode['exclude'][which].get(f, 0) + by_mode['only'][which].get(f, 0)), f


def test_has_cycles_in_the_fan_in_view_keeps_the_cycle_rule(project):
    """fan-in counts lazy edges; its has_cycles still uses the cycle rule (lazy left out)."""
    rings = _tree(project.parent / 'rings', {k: FILES[k] for k in ('ring_a.py', 'ring_b.py')})
    data = _json(_uri(rings, 'rank=fan-in'))
    assert _ranks(data)[0] == {'ring_a.py': 1, 'ring_b.py': 1}
    assert data['metadata']['has_cycles'] is False
    assert data['metadata']['cycles_lazy'] == 'exclude'
    assert _json(_uri(rings, 'rank=fan-in&lazy=include'))['metadata']['has_cycles'] is True


def test_entrypoints_and_components_count_lazy_edges(project):
    entry = {to_posix(e['file']) for e in _json(_uri(project, 'entrypoints'))['entries']}
    assert 'ring_a.py' not in entry  # its only importer is ring_b's lazy import
    assert 'ring_a.py' in {to_posix(e['file'])
                           for e in _json(_uri(project, 'entrypoints&lazy=exclude'))['entries']}
    components = _json(_uri(project, 'components'))
    assert components['edge_rule']['lazy'] == 'include'
    (row,) = components['components']
    assert row['internal'] == 8  # every edge but typed's TYPE_CHECKING import
    assert _json(_uri(project, 'components&lazy=exclude'))['components'][0]['internal'] == 6


def test_unknown_lazy_value_is_rejected_before_graph_work(project, monkeypatch):
    calls = []
    monkeypatch.setattr(ImportsAdapter, '_build_graph', lambda *args: calls.append(args))
    with pytest.raises(ValueError, match=r"lazy must be one of .*include.*exclude.*only.*'sometimes'"):
        ImportsAdapter(str(project), 'circular&lazy=sometimes').get_structure()
    assert calls == []


def test_unknown_lazy_value_fails_the_cli(project):
    out = _run_reveal_direct(_uri(project, 'circular&lazy=sometimes'))
    assert out.returncode == 1
    assert 'lazy must be one of' in out.stderr


def test_schema_declares_lazy():
    spec = ImportsAdapter.get_schema()['query_params']['lazy']
    assert spec['choices'] == ['include', 'exclude', 'only']


# ------------------------------------------------------------------ printed rule (text)

def test_text_prints_the_rule(project):
    fan_in = _run(_uri(project, 'rank=fan-in'))
    assert 'Rule:' in fan_in and 'function-level (lazy) imports included' in fan_in
    assert 'TYPE_CHECKING imports excluded' in fan_in
    circular = _run(_uri(project, 'circular'))
    assert 'Rule:' in circular and 'function-level (lazy) imports excluded' in circular
    assert '&lazy=include' in circular
    only = _run(_uri(project, 'rank=fan-in&lazy=only'))
    assert 'only function-level (lazy) imports' in only
    summary = _run(f'imports://{to_posix(project)}')
    assert 'Rule:' in summary


def test_depends_prints_its_rule(project):
    r = to_posix(project)
    data = _json(f'depends://{r}/core.py?root={r}')
    assert sorted(to_posix(d['file']) for d in data['dependents']) == ['both.py', 'eager.py', 'lazy.py']
    rule = data['edge_rule']
    assert (rule['lazy'], rule['type_checking'], rule['tests']) == ('include', 'excluded', 'included')
    text = _run(f'depends://{r}/core.py?root={r}')
    assert 'Rule:' in text and 'function-level (lazy) imports included' in text


def test_unclassified_language_is_disclosed(tmp_path):
    """Only Python records import scope today: a JS edge is counted under every &lazy
    value, and the rule names the language instead of claiming the filter covered it."""
    root = _tree(tmp_path / 'mixed', {
        'a.js': 'export const x = 1;\n',
        'b.js': "export function f() { return import('./a.js'); }\n",
        'p.py': 'X = 1\n', 'q.py': 'def f():\n    import p\n',
    })
    for lazy, fan_in in (('include', {'a.js': 1, 'p.py': 1}), ('exclude', {'a.js': 1}), ('only', {'p.py': 1})):
        data = _json(_uri(root, f'rank=fan-in&lazy={lazy}'))
        assert _ranks(data)[0] == fan_in, lazy
        assert data['edge_rule']['unclassified_edges'] == 1
        assert data['edge_rule']['unclassified_languages'] == ['javascript']
    text = _run(_uri(root, 'rank=fan-in&lazy=exclude'))
    assert 'scope is not recorded for javascript' in text


# ------------------------------------------------------------------ I002 keeps BACK-445

def _i002_flagged(root):
    flagged = set()
    for path in sorted(root.rglob('*.py')):
        if I002().check(str(path), None, path.read_text(encoding='utf-8')):
            flagged.add(path.relative_to(root).as_posix())
    return flagged


def test_i002_does_not_flag_a_lazy_back_edge(tmp_path):
    root = _tree(tmp_path / 'lazy', {k: FILES[k] for k in ('ring_a.py', 'ring_b.py')})
    assert _i002_flagged(root) == set()


def test_i002_flags_only_the_load_time_cycle(project):
    """Negative control for the control: the module-level loop is still a cycle."""
    assert _i002_flagged(project) == {'loop_a.py', 'loop_b.py'}


def test_i002_graph_keeps_the_lazy_edge(project):
    """I002 resolves through resolve_graph (BACK-1723): the edge is stored, tagged local."""
    I002().check(str(project / 'ring_b.py'), None, FILES['ring_b.py'])
    (graph,) = _graph_cache.values()
    assert project / 'ring_a.py' in graph.dependencies[project / 'ring_b.py']
    assert graph.edge_scopes[(project / 'ring_b.py', project / 'ring_a.py')] == {'local'}
