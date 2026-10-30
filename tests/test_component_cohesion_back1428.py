"""Component cohesion is declined where files see each other without importing (BACK-1428).

cohesion = internal / (internal + outgoing) imports. In Go, Java, Kotlin, C#, Scala and Swift the files of one
package or module reference each other with no import, so `internal` is structurally ~0 and every large component
printed 0.00 (kubernetes vendor/golang.org/x/sys/unix, 284 files; tivi data/models). The number is declined, not
replaced by a substitute metric; Python, JS/TS, Ruby, PHP, Rust, C and C++ keep theirs.
"""
import json
from pathlib import Path

import pytest

from reveal.adapters.imports import ImportsAdapter
from conftest import _run_reveal_direct as run


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _components(root: Path) -> dict:
    result = ImportsAdapter(str(root), 'components').get_structure()
    return {Path(c['component']).name: c for c in result['components']}, result


@pytest.fixture
def go_tree(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'util' / 'a.go', 'package util\n\nfunc A() int { return 1 }\n')
    _w(root / 'util' / 'b.go', 'package util\n\nfunc B() int { return A() + 1 }\n')
    _w(root / 'main.go', 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println(1) }\n')
    return root


@pytest.fixture
def py_tree(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'a.py', 'from pkg import b\n\n\ndef a():\n    return b.b()\n')
    _w(root / 'pkg' / 'b.py', 'def b():\n    return 1\n')
    _w(root / 'other.py', 'from pkg import a\n\n\ndef o():\n    return a.a()\n')
    return root


def test_go_package_cohesion_is_declined_not_zero(go_tree):
    comps, result = _components(go_tree)
    util = comps['util']
    assert util['files'] == 2
    assert util['cohesion'] is None, f"two files of one Go package printed {util['cohesion']}"
    assert 'cohesion_reason' in util
    assert result['cohesion_rule']  # the rule is said once, on the response


def test_kotlin_package_cohesion_is_declined_not_zero(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'models' / 'A.kt', 'package app.models\n\nclass A\n')
    _w(root / 'models' / 'B.kt', 'package app.models\n\nclass B(val a: A)\n')
    comps, _ = _components(root)
    assert comps['models']['cohesion'] is None


def test_declined_components_are_not_ranked_among_measured_ones(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'gopkg' / 'a.go', 'package g\n\nfunc A() {}\n')
    _w(root / 'gopkg' / 'b.go', 'package g\n\nfunc B() {}\n')
    _w(root / 'gopkg' / 'c.go', 'package g\n\nfunc C() {}\n')
    _w(root / 'pylow' / 'x.py', 'import os\n\n\ndef x():\n    return os\n')
    _w(root / 'pylow' / 'y.py', 'import sys\n\n\ndef y():\n    return sys\n')
    result = ImportsAdapter(str(root), 'components').get_structure()
    order = [Path(c['component']).name for c in result['components']]
    # a measured 0.0 (python imports only the stdlib) ranks ahead of a declined Go package of more files
    assert order == ['pylow', 'gopkg']


def test_negative_control_python_cohesion_keeps_its_number_and_adds_no_key(py_tree):
    comps, result = _components(py_tree)
    assert comps['pkg'] == {'component': 'pkg', 'files': 2, 'internal': 1, 'outgoing': 1,
                            'incoming': 1, 'cohesion': 0.5, 'top_bridge': 'pkg/a.py'}
    assert 'cohesion_rule' not in result


def test_mixed_directory_rule_is_a_strict_majority_of_files(tmp_path):
    mostly_go = tmp_path / 'a'
    for name in ('x.go', 'y.go'):
        _w(mostly_go / 'd' / name, 'package d\n')
    _w(mostly_go / 'd' / 'z.py', 'import os\n')
    mostly_py = tmp_path / 'b'
    _w(mostly_py / 'd' / 'x.go', 'package d\n')
    for name in ('y.py', 'z.py'):
        _w(mostly_py / 'd' / name, 'import os\n')
    even = tmp_path / 'c'
    _w(even / 'd' / 'x.go', 'package d\n')
    _w(even / 'd' / 'y.py', 'import os\n')
    assert _components(mostly_go)[0]['d']['cohesion'] is None
    assert _components(mostly_py)[0]['d']['cohesion'] == 0.0
    assert _components(even)[0]['d']['cohesion'] == 0.0  # exactly half is not a majority


def test_overview_text_says_n_a_once_with_the_reason(go_tree):
    out = run('overview', str(go_tree)).stdout
    section = out.split('Major components', 1)[1].split('Cycle groups', 1)[0]
    assert '0.00' not in section
    assert section.count('n/a') >= 2  # one per declined row
    assert section.count('same-package') == 1  # the reason once, not per row


def test_overview_json_carries_null_cohesion_and_the_rule(go_tree):
    data = json.loads(run('overview', str(go_tree), '--format', 'json').stdout)
    arch = data['map']
    assert all(c['cohesion'] is None for c in arch['components']['rows'])
    assert arch['rules']['cohesion_rule']


def test_imports_components_text_shows_n_a_not_zero_percent(go_tree):
    out = run(f'imports://{go_tree}?components').stdout
    assert '0%' not in out
    assert 'n/a' in out


def test_architecture_brief_declines_too(go_tree):
    out = run('architecture', str(go_tree)).stdout
    section = out.split('Major components', 1)[1]
    assert '0.00' not in section.split('\n\n', 1)[0]
    assert 'n/a' in section


def test_python_overview_preserves_component_numbers(py_tree):
    out = run('overview', str(py_tree)).stdout
    assert 'Major components  (showing 2 of 2 observed)' in out
    assert 'pkg  2 files; internal 1, outgoing 1, incoming 1; cohesion 0.5' in out
    assert 'n/a' not in out
