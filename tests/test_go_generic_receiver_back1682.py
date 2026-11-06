"""BACK-1682: a Go method on a generic receiver (``func (s St[K]) Len()``, ``func (s *St[K]) Put()``)
belongs to ``St`` like any other method: the receiver's ``generic_type`` wraps the type name."""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

SOURCE = (
    'package p\n\n'
    'type St[K comparable, V any] struct{ m map[K]V }\n\n'
    'func (s St[K, V]) Len() int { return len(s.m) }\n\n'
    'func (s *St[K, V]) Put(k K, v V) { s.m[k] = v }\n\n'
    'type Plain struct{}\n\n'
    'func (p Plain) Name() string { return "x" }\n\n'
    'func Free() {}\n'
)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'g.go'
    path.write_text(SOURCE, encoding='utf-8')
    return path


def test_ast_owner_of_generic_receiver_methods(source):
    data = json.loads(_run_reveal_direct(f'ast://{source}?type=function', '--format', 'json').stdout)
    owners = {r['name']: r.get('owner') for r in data['results']}
    assert owners['Len'] == 'St' and owners['Put'] == 'St'
    assert owners['Name'] == 'Plain'  # control: plain receiver
    assert not owners.get('Free')     # control: no receiver


def test_outline_nests_generic_receiver_methods(source):
    lines = _run_reveal_direct(str(source), '--outline').stdout.splitlines()
    st = next(i for i, line in enumerate(lines) if line.startswith('St'))
    plain = next(i for i, line in enumerate(lines) if line.startswith('Plain'))
    nested = [line for line in lines[st + 1:plain] if '└─' in line or '├─' in line]
    assert any('Len' in line for line in nested) and any('Put' in line for line in nested), lines


def test_qualified_element_lookup(source):
    result = _run_reveal_direct(str(source), 'St.Len')
    assert result.returncode == 0, result.stderr
    assert 'return len(s.m)' in result.stdout
