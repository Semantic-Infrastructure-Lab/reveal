"""I002 judges a load-time import cycle only where one breaks the program (BACK-2156).

Importing runs the imported file's top level in order in Python, JavaScript/TypeScript, PHP, Lua
and Ruby, so a cycle there leaves a module half-initialized (or raises). In Rust, Zig, Java, Kotlin,
C#, Scala, Dart and Swift a cycle is legal, and Go rejects one at compile time: I002 does not
report those files, and the run says so (W-CAP-3) and names the command that shows the cycles
as an architecture fact. Scott chose this narrowing on 2026-11-03.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.rules.imports.I002 import _graph_cache


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    _graph_cache.clear()
    yield
    _graph_cache.clear()


RUST_CYCLE = {
    'Cargo.toml': '[package]\nname = "probe"\nversion = "0.1.0"\n',
    'src/lib.rs': 'mod a;\nmod b;\n',
    'src/a.rs': 'use crate::b::B;\npub struct A;\n',
    'src/b.rs': 'use crate::a::A;\npub struct B;\n',
}

PY_CYCLE = {
    'pyproject.toml': '[project]\nname = "probe"\n',
    'p.py': 'import q\n',
    'q.py': 'import p\n',
}

TS_CYCLE = {
    'package.json': '{"name": "probe"}\n',
    'm.ts': "import { n } from './n';\nexport const m = 1;\n",
    'n.ts': "import { m } from './m';\nexport const n = 2;\n",
}


def _tree(root, files):
    root.mkdir()
    root = root.resolve()
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _check(root):
    run = _run_reveal_direct('check', str(root), '--select', 'I002', '--format', 'json')
    data = json.loads(run.stdout)
    found = sorted(f['file'].replace('\\', '/').rsplit('/', 1)[-1]
                   for f in data['files'] for d in f.get('detections') or [] if d['rule_code'] == 'I002')
    return run.returncode, found, data['summary'].get('scan_disclosures') or []


def test_a_rust_module_cycle_is_not_an_i002_finding(tmp_path):
    root = _tree(tmp_path / 'r', RUST_CYCLE)
    code, found, disclosures = _check(root)
    assert found == []
    assert code == 0
    note = [d for d in disclosures if d.startswith('W-CAP-3')]
    assert len(note) == 1 and 'I002' in note[0] and 'rust' in note[0] and '?circular' in note[0]


def test_the_rust_cycle_is_still_reported_by_imports_circular(tmp_path):
    root = _tree(tmp_path / 'r', RUST_CYCLE)
    run = _run_reveal_direct(f'imports://{root}?circular', '--format', 'json')
    assert json.loads(run.stdout)['count'] == 1


@pytest.mark.parametrize('files,expected', [(PY_CYCLE, ['p.py', 'q.py']), (TS_CYCLE, ['m.ts', 'n.ts'])],
                         ids=['python', 'typescript'])
def test_load_order_languages_still_report_their_cycles(tmp_path, files, expected):
    root = _tree(tmp_path / 't', files)
    code, found, disclosures = _check(root)
    assert found == expected
    assert code == 1
    assert not [d for d in disclosures if d.startswith('W-CAP-3')]


def test_a_mixed_tree_reports_python_and_discloses_rust(tmp_path):
    root = _tree(tmp_path / 'mix', {**RUST_CYCLE, **PY_CYCLE})
    code, found, disclosures = _check(root)
    assert found == ['p.py', 'q.py']
    assert code == 1
    assert any(d.startswith('W-CAP-3') and 'rust (3)' in d for d in disclosures), disclosures
