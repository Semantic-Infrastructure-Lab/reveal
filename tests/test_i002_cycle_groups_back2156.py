"""BACK-2156: ``reveal check``'s I002 and ``imports://?circular`` answer one question, so they must
read one graph and agree on which files sit in a load-time cycle.

At d22a74c3 I002 built its own graph (its own extraction, then ``service.resolve_graph``), while
``?circular`` reads the analysis service's build (``service.analyze``, the resolution cascade). The
cascade finds edges ``resolve_graph`` never does (a PHP ``require`` through a ``define()`` constant,
C# namespaces, Kotlin/Scala members), so a cycle ``?circular`` reports can be invisible to ``check``.

The counting unit differs too: ``?circular`` counts cycle groups (strongly connected components);
I002 reports one finding per member file for every cycle its DFS meets (one per back edge), so a
group of three files with several elementary cycles gives several findings per file. Which unit
``check`` should report is a pending decision (the per-file contract of ``check``, ``--changed`` and
single-file checks), pinned below as a strict xfail.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.rules.imports.I002 import _graph_cache
from reveal.utils.path_utils import to_posix

PYPROJECT = {'pyproject.toml': '[project]\nname = "probe"\n'}

# Two load-time groups. {a, b, c} imports each other both ways: five elementary cycles (three of two
# files, two of three), {x, y} one. ``leaf`` imports into the group and is in no cycle.
TWO_GROUPS = {
    **PYPROJECT,
    'a.py': 'import b\nimport c\n',
    'b.py': 'import a\nimport c\n',
    'c.py': 'import a\nimport b\n',
    'x.py': 'import y\n',
    'y.py': 'import x\n',
    'leaf.py': 'import a\n',
}

ACYCLIC = {**PYPROJECT, 'a.py': 'import b\n', 'b.py': 'import c\n', 'c.py': 'X = 1\n'}

# ``lazy_a -> lazy_b`` is module level and ``lazy_b -> lazy_a`` sits in a function body, so the pair
# is a cycle only under &lazy=include.
LAZY_ONLY = {
    **PYPROJECT,
    'lazy_a.py': 'import lazy_b\n',
    'lazy_b.py': 'def f():\n    import lazy_a\n    return lazy_a\n',
}

# PHP: a.php loads b.php through a define() constant (the cascade's 'constant' stage), b.php loads
# a.php directly. One load-time group {a.php, b.php}.
PHP_CONSTANT_CYCLE = {
    'composer.json': '{}\n',
    'config.php': "<?php\ndefine('BASE', __DIR__ . '/');\n",
    'a.php': "<?php\nrequire_once BASE . 'b.php';\n",
    'b.php': "<?php\nrequire_once __DIR__ . '/a.php';\n",
    'leaf.php': "<?php\nrequire_once __DIR__ . '/a.php';\n",
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
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _check(root):
    """(exit code, {file name: [I002 detections]}) of ``reveal check ROOT --select I002``."""
    out = _run_reveal_direct('check', root, '--select', 'I002', '--format', 'json')
    data = json.loads(out.stdout)
    found = {}
    for record in data['files']:
        hits = [d for d in record.get('detections', []) if d['rule_code'] == 'I002']
        if hits:
            found[to_posix(record['file']).rsplit('/', 1)[-1]] = hits
    return out.returncode, found


def _circular(root, query='circular'):
    out = _run_reveal_direct(f'imports://{to_posix(root)}?{query}', '--format', 'json')
    assert out.returncode in (0, 1), out.stderr
    data = json.loads(out.stdout)
    groups = sorted(sorted(to_posix(p).rsplit('/', 1)[-1] for p in group) for group in data['cycles'])
    return data, groups


def _members(groups):
    return {name for group in groups for name in group}


def test_check_flags_the_files_of_circular_groups(tmp_path):
    """Negative control on the language the cascade and resolve_graph already agree on: both
    commands put the same five files in a cycle."""
    root = _tree(tmp_path / 'p', TWO_GROUPS)
    _code, found = _check(root)
    data, groups = _circular(root)
    assert groups == [['a.py', 'b.py', 'c.py'], ['x.py', 'y.py']]
    assert data['count'] == 2
    assert set(found) == _members(groups)


def test_a_cycle_through_a_php_define_constant_is_a_check_finding(tmp_path):
    """The cascade resolves ``require_once BASE . 'b.php'`` (via 'constant'); resolve_graph does
    not, so at d22a74c3 ``?circular`` reports the group and ``check`` reports no file of it."""
    root = _tree(tmp_path / 'php', PHP_CONSTANT_CYCLE)
    data, groups = _circular(root)
    assert groups == [['a.php', 'b.php']]
    code, found = _check(root)
    assert set(found) == {'a.php', 'b.php'}
    assert code == 1


def test_one_finding_per_file_per_group_names_its_group(tmp_path):
    """Option B (BACK-2156): a file in a cycle group reports once, whatever number of
    elementary cycles run through it, and the message states the group and the rule."""
    root = _tree(tmp_path / 'p', TWO_GROUPS)
    _code, found = _check(root)
    data, groups = _circular(root)
    assert {name: len(hits) for name, hits in found.items()} == {n: 1 for n in _members(groups)}
    size = {name: len(group) for group in groups for name in group}
    for name, (hit,) in found.items():
        assert f'of {data["count"]} ({size[name]} files; one finding per file per group' in hit['message']
        cycle = hit['context'].removeprefix('Import cycle: ').split(' -> ')
        assert cycle[0] == cycle[-1] == name and len(set(cycle[:-1])) == len(cycle) - 1


@pytest.mark.xfail(strict=True, reason='BACK-2156: check reports one finding per file per cycle group '
                   '(Scott chose option B, 2026-11-03); one finding per group in every invocation form '
                   'needs the run\'s file set in the rules (option C, follow-up)')
def test_check_counts_what_circular_counts(tmp_path):
    root = _tree(tmp_path / 'p', TWO_GROUPS)
    _code, found = _check(root)
    data, _groups = _circular(root)
    assert sum(len(hits) for hits in found.values()) == data['count']


def test_an_acyclic_tree_is_clean_in_both(tmp_path):
    root = _tree(tmp_path / 'p', ACYCLIC)
    code, found = _check(root)
    data, groups = _circular(root)
    assert (code, found) == (0, {})
    assert (data['count'], groups) == (0, [])


def test_a_lazy_only_cycle_follows_the_circular_default(tmp_path):
    """The function-level back edge closes no load-time cycle: neither command reports it by
    default, and ?circular&lazy=include shows the group the default leaves out."""
    root = _tree(tmp_path / 'p', LAZY_ONLY)
    code, found = _check(root)
    data, groups = _circular(root)
    assert (code, found) == (0, {})
    assert groups == [] and data['edge_rule']['lazy'] == 'exclude'
    _data, included = _circular(root, 'circular&lazy=include')
    assert included == [['lazy_a.py', 'lazy_b.py']]


def test_a_partial_index_still_exits_3(tmp_path):
    """BACK-1826: a sibling that fails to parse leaves the graph incomplete, so the clean file's
    no-cycle answer may be wrong: exit 3 with the disclosure, not 0."""
    root = _tree(tmp_path / 'p', {**ACYCLIC, 'broken.ts': 'export const x = (;\nimport { a } from "./c";\n'})
    out = _run_reveal_direct('check', root / 'a.py', '--select', 'I002', '--format', 'json')
    data = json.loads(out.stdout)
    assert out.returncode == 3
    assert data['detections'] == []
    assert any(line.startswith('I002: 1 file(s) under ') and 'parsed with errors' in line
               for line in data['scan_disclosures'])
