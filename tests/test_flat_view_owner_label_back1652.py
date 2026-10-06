"""BACK-1652: the default (non-outline) view listed a Go receiver or Rust impl method
as a bare name, so `Run(order)` (a function) and `Run(items)` (Batch's method) were
two indistinguishable `Run` rows. A member row now carries its owner (`Batch.Run`),
the address `reveal f Batch.Run` resolves. Text only: JSON items already carry `owner`.
"""

import json
import subprocess
import sys

import pytest

_SAMPLES = {
    'a.go': ('package p\n\ntype Batch struct{ n int }\n\n'
             'func Run(order string) {}\n\nfunc (b *Batch) Run(items []int) {}\n',
             ['Run(order string)', 'Batch.Run(items []int)']),
    'a.rs': ('struct Batch { n: i32 }\n\nfn run(order: i32) {}\n\n'
             'impl Batch {\n    fn run(&self, items: i32) {}\n}\n',
             ['run(order: i32)', 'Batch.run(&self, items: i32)']),
    'a.py': ('def run(order):\n    pass\n\n\nclass Batch:\n    def run(self, items):\n        pass\n',
             ['run(order)', 'Batch.run(self, items)']),
}


def _reveal(path, *args):
    proc = subprocess.run([sys.executable, '-m', 'reveal', str(path), *args],
                          capture_output=True, text=True, timeout=120, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.mark.parametrize('name', sorted(_SAMPLES))
def test_flat_view_labels_a_member_with_its_owner(tmp_path, name):
    source, rows = _SAMPLES[name]
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    lines = [line.split(None, 1)[1] for line in _reveal(path).splitlines()
             if line.startswith('  :')]
    assert any(line.startswith(rows[0]) for line in lines), lines
    assert any(line.startswith(rows[1]) for line in lines), lines


@pytest.mark.parametrize('name', sorted(_SAMPLES))
def test_json_names_stay_bare_and_carry_owner(tmp_path, name):
    source, _ = _SAMPLES[name]
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    funcs = json.loads(_reveal(path, '--format', 'json'))['structure']['functions']
    assert [f['name'] for f in funcs] == [funcs[0]['name']] * 2
    assert [f.get('owner') for f in funcs] == [None, 'Batch']


def test_outline_view_is_unchanged(tmp_path):
    path = tmp_path / 'a.go'
    path.write_text(_SAMPLES['a.go'][0], encoding='utf-8')
    out = _reveal(path, '--outline')
    assert 'Batch.Run' not in out
    assert '└─ Run(items []int)' in out
