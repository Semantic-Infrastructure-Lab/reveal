"""BACK-1732: diff:// must never report a silent clean.

The compare step looked at functions, classes and imports only, so every other element
category a code analyzer emits -- Go and TypeScript interfaces, Rust structs, enums and
traits, TypeScript type aliases -- was invisible, and a pair of files differing only there
printed "No structural changes detected", exit 0. A Python module-level constant is not in
the structure at all; a pair differing only there must say the sources differ in something
diff:// does not compare, not call them equal.

Negative controls: identical files are still clean (no warning), and a pure
function/class/import change renders byte-for-byte as before.
"""

import json
import subprocess
import sys

import pytest

from reveal.diff import compute_structure_diff


def _reveal(cwd, *args):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


PAIRS = {
    'go': ('package m\n\nfunc A() int { return 1 }\n',
           'package m\n\nfunc A() int { return 1 }\n'
           'type Shape interface {\n\tArea() float64\n}\n'),
    'rs': ('fn a() -> i32 { 1 }\n',
           'fn a() -> i32 { 1 }\nstruct P { x: i32 }\nenum E { A, B }\ntrait T { fn f(&self); }\n'),
    'ts': ('function a(): number { return 1; }\n',
           'function a(): number { return 1; }\ninterface I { x: number }\n'
           'type U = string | number;\n'),
    'py': ('X = 1\n', 'X = 2\nY = 3\n'),
}

# What each pair adds, by the category its analyzer files it under (a Rust trait is an
# interface). Python's analyzer emits no category for a module-level constant.
ADDED = {
    'go': {'interfaces': ['Shape']},
    'rs': {'structs': ['P'], 'enums': ['E'], 'interfaces': ['T']},
    'ts': {'interfaces': ['I'], 'types': ['U']},
}


@pytest.fixture
def pairs(tmp_path):
    for ext, (left, right) in PAIRS.items():
        (tmp_path / f'a.{ext}').write_text(left, encoding='utf-8')
        (tmp_path / f'b.{ext}').write_text(right, encoding='utf-8')
    return tmp_path


def _json(cwd, uri):
    proc = _reveal(cwd, uri, '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _warnings(result):
    return [w for w in (result.get('meta') or {}).get('warnings', []) if isinstance(w, dict)]


def _change_count(result):
    return sum(n for bucket in result['summary'].values() for n in bucket.values())


@pytest.mark.parametrize('ext', ['go', 'rs', 'ts'])
def test_added_type_categories_are_reported(pairs, ext):
    result = _json(pairs, f'diff://a.{ext}:b.{ext}')
    for category, names in ADDED[ext].items():
        assert result['summary'][category] == {'added': len(names), 'removed': 0, 'modified': 0}
        assert [(d['type'], d['name']) for d in result['diff'][category]] == \
            [('added', n) for n in names]


@pytest.mark.parametrize('ext', ['go', 'rs', 'ts'])
def test_added_type_categories_render_in_text(pairs, ext):
    proc = _reveal(pairs, f'diff://a.{ext}:b.{ext}')
    assert proc.returncode == 0, proc.stderr
    assert 'No structural changes detected' not in proc.stdout
    for category, names in ADDED[ext].items():
        assert f'  {category.capitalize()}:  +{len(names)} -0' in proc.stdout
        for name in names:
            assert f'  + {name}\n' in proc.stdout


@pytest.mark.parametrize('ext', ['go', 'rs', 'ts'])
def test_removed_type_categories_are_reported(pairs, ext):
    result = _json(pairs, f'diff://b.{ext}:a.{ext}')
    for category, names in ADDED[ext].items():
        assert result['summary'][category]['removed'] == len(names)


def test_python_constant_change_is_disclosed_not_clean(pairs):
    result = _json(pairs, 'diff://a.py:b.py')
    assert _change_count(result) == 0  # the analyzer has no constant category to compare
    notes = [w for w in _warnings(result) if w.get('type') == 'not_compared']
    assert len(notes) == 1
    assert 'a.py' in notes[0]['message'] and 'b.py' in notes[0]['message']


def test_python_constant_change_text_says_so(pairs):
    proc = _reveal(pairs, 'diff://a.py:b.py')
    assert proc.returncode == 0, proc.stderr
    assert '⚠' in proc.stdout
    assert 'differ' in proc.stdout


def test_changed_interface_is_modified(tmp_path):
    (tmp_path / 'a.go').write_text(
        'package m\n\ntype Shape interface {\n\tArea() float64\n}\n', encoding='utf-8')
    (tmp_path / 'b.go').write_text(
        'package m\n\ntype Shape interface {\n\tArea() float64\n\tPerimeter() float64\n}\n',
        encoding='utf-8')
    result = _json(tmp_path, 'diff://a.go:b.go')
    assert result['summary']['interfaces'] == {'added': 0, 'removed': 0, 'modified': 1}
    (detail,) = result['diff']['interfaces']
    assert detail['type'] == 'modified' and detail['name'] == 'Shape'
    assert detail['changes']['line_count'] == {'old': 3, 'new': 4}


def test_moved_interface_is_not_modified(tmp_path):
    """Position alone is not a change: an interface pushed down by a new function."""
    body = 'type Shape interface {\n\tArea() float64\n}\n'
    (tmp_path / 'a.go').write_text('package m\n\n' + body, encoding='utf-8')
    (tmp_path / 'b.go').write_text('package m\n\nfunc A() int { return 1 }\n' + body,
                                   encoding='utf-8')
    result = _json(tmp_path, 'diff://a.go:b.go')
    assert result['summary']['functions']['added'] == 1
    assert result['summary']['interfaces'] == {'added': 0, 'removed': 0, 'modified': 0}


def test_category_without_names_is_disclosed_not_dropped():
    """A list category whose items carry no name cannot be matched item by item: say so."""
    left = {'functions': [], 'widgets': [{'line': 1, 'x': 1}]}
    right = {'functions': [], 'widgets': [{'line': 1, 'x': 2}]}
    assert compute_structure_diff(left, right)['not_compared'] == ['widgets']
    assert compute_structure_diff(left, left)['not_compared'] == []


def test_metadata_keys_are_not_categories():
    """Scalars and dicts (an envelope's type/source/meta, batch's stats) are not elements."""
    left = {'type': 'zig_structure', 'source': 'a.zig', 'meta': {'x': 1},
            'functions': [{'name': 'f', 'line': 1}]}
    right = dict(left, source='b.zig', meta={'x': 2})
    diff = compute_structure_diff(left, right)
    assert set(diff['summary']) == {'functions', 'classes', 'imports'}
    assert diff['not_compared'] == []


def test_git_directory_diff_sees_added_interface(tmp_path, monkeypatch):
    pygit2 = pytest.importorskip('pygit2')
    repo_dir = tmp_path / 'repo'
    repo_dir.mkdir()
    repo = pygit2.init_repository(str(repo_dir))
    author = pygit2.Signature('Test', 'test@example.com')
    source = repo_dir / 'm.go'
    parents = []
    for text in PAIRS['go']:
        source.write_text(text, encoding='utf-8')
        repo.index.add_all()
        repo.index.write()
        tree = repo.index.write_tree()
        parents = [repo.create_commit('HEAD', author, author, 'c', tree, parents)]
    monkeypatch.chdir(repo_dir)
    from reveal.adapters.diff.adapter import DiffAdapter
    result = DiffAdapter('git://HEAD~1/.:git://HEAD/.').get_structure()
    assert result['summary']['interfaces'] == {'added': 1, 'removed': 0, 'modified': 0}


def test_directory_diff_sees_added_interface(tmp_path):
    for side, text in zip(('d1', 'd2'), PAIRS['go']):
        (tmp_path / side).mkdir()
        (tmp_path / side / 'm.go').write_text(text, encoding='utf-8')
    result = _json(tmp_path, 'diff://d1:d2')
    assert result['summary'].get('interfaces', {}).get('added') == 1


# Negative controls.
@pytest.mark.parametrize('ext', ['go', 'rs', 'ts', 'py'])
def test_identical_files_stay_clean(pairs, ext):
    result = _json(pairs, f'diff://b.{ext}:b.{ext}')
    assert _change_count(result) == 0
    assert _warnings(result) == []
    proc = _reveal(pairs, f'diff://b.{ext}:b.{ext}')
    assert 'No structural changes detected' in proc.stdout
    assert '⚠' not in proc.stdout


FUNC_LEFT = ('import os\n\n\ndef f(x):\n    return x\n\n\n'
             'class C:\n    def m(self):\n        return 1\n')
FUNC_RIGHT = ('import os\nimport sys\n\n\ndef f(x, y):\n    return x + y\n\n\n'
              'def g():\n    return 2\n\n\nclass C(object):\n    def m(self):\n        return 1\n')

# Captured on master d2ff8b5e (before BACK-1732): the function/class/import render is unchanged.
FUNC_GOLDEN = """
======================================================================
Structure Diff: fa.py → fb.py
======================================================================

📊 Summary:

  Functions:  +1 -0 ~1
  Classes:  +0 -0 ~1
  Imports:  +1 -0

🔧 Functions:

  + g
      Line 9
      ()
      [NEW - 2 lines, complexity 1]

  ~ f
      Signature:
        - (x)
        + (x, y)
      Line: 4 → 5

📦 Classes:

  ~ C
      Bases:
        - (none)
        + object

📥 Imports:

  + import sys


---

  1. reveal 'diff://fa.py:fb.py/f'
     └─ Deep dive into f changes

Next: reveal stats://fb.py      # Analyze complexity trends
      reveal check fb.py      # Check quality after changes
      reveal help://diff         # Learn more about diff adapter
"""


@pytest.fixture
def func_pair(tmp_path):
    (tmp_path / 'fa.py').write_text(FUNC_LEFT, encoding='utf-8')
    (tmp_path / 'fb.py').write_text(FUNC_RIGHT, encoding='utf-8')
    return tmp_path


def test_function_change_text_is_byte_identical(func_pair):
    proc = _reveal(func_pair, 'diff://fa.py:fb.py')
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == FUNC_GOLDEN


def test_function_change_json_shape_is_unchanged(func_pair):
    result = _json(func_pair, 'diff://fa.py:fb.py')
    assert result['summary'] == {
        'functions': {'added': 1, 'removed': 0, 'modified': 1},
        'classes': {'added': 0, 'removed': 0, 'modified': 1},
        'imports': {'added': 1, 'removed': 0},
    }
    assert list(result['diff']) == ['functions', 'classes', 'imports']
    assert _warnings(result) == []
