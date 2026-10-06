"""BACK-1651: a Go named non-struct type is a structure item, so its methods nest.

`type T int` / `type F func()` / `type M map[..]..` / `type A = B` were not in the
structure at all, so `func (t T) String()` had no container and listed flat. They now
join the existing `types` declaration category (Rust `type`, Kotlin typealias) and the
owner nesting of BACK-1632 applies unchanged.
"""

import json
import subprocess
import sys

import pytest

from reveal.display.outline import build_hierarchy
from reveal.registry import get_analyzer

_GO = """package p

type Batch struct{ n int }
type Shape interface{ Area() float64 }
type T int
type F func()
type M map[string]int
type Alias = Batch
type (
	A int
	B struct{ x int }
)
type Set[K comparable] map[K]struct{}

func (b *Batch) Run() int { return b.n }
func (t T) String() string { return "t" }
func (f F) Call() { f() }
func (s Set[K]) Len() int { return len(s) }
func helper() {}
"""


@pytest.fixture
def go_file(tmp_path):
    path = tmp_path / 'a.go'
    path.write_text(_GO, encoding='utf-8')
    return path


def _structure(path):
    return get_analyzer(str(path))(str(path)).get_structure()


def test_named_non_struct_types_are_structure_items(go_file):
    types = _structure(go_file)['types']
    assert [t['name'] for t in types] == ['T', 'F', 'M', 'Alias', 'A', 'Set']
    assert [t['line'] for t in types] == [5, 6, 7, 8, 10, 13]


def test_structs_and_interfaces_are_not_duplicated_under_types(go_file):
    structure = _structure(go_file)
    assert [s['name'] for s in structure['structs']] == ['Batch', 'B']
    assert [i['name'] for i in structure['interfaces']] == ['Shape']
    assert not {'Batch', 'B', 'Shape'} & {t['name'] for t in structure.get('types', [])}


def test_file_without_named_types_has_no_types_category(tmp_path):
    path = tmp_path / 'b.go'
    path.write_text('package p\n\ntype S struct{}\n\nfunc f() {}\n', encoding='utf-8')
    assert 'types' not in _structure(path)


def test_methods_nest_under_their_named_type(go_file):
    structure = {k: v for k, v in get_analyzer(str(go_file))(str(go_file)).get_outline().items()
                 if k != 'imports'}

    def shape(items):
        return [(i['name'], shape(i['children'])) for i in items]
    assert shape(build_hierarchy(structure)) == [
        ('Batch', [('Run', [])]), ('Shape', []),
        ('T', [('String', [])]), ('F', [('Call', [])]), ('M', []), ('Alias', []),
        ('A', []), ('B', []), ('Set', [('Len', [])]), ('helper', []),
    ]


def test_named_type_extracts_by_name_and_method_by_path(go_file):
    from reveal.display.element import _extract_by_syntax, _parse_element_syntax

    analyzer = get_analyzer(str(go_file))(str(go_file))

    def extract(element):
        return _extract_by_syntax(analyzer, element, _parse_element_syntax(element))
    assert extract('F')['source'].strip() == 'type F func()'
    assert extract('T.String')['line_start'] == 16


def test_text_and_json_views_agree(go_file):
    def run(*args):
        return subprocess.run([sys.executable, '-m', 'reveal', str(go_file), *args],
                              capture_output=True, text=True, timeout=120, encoding='utf-8')
    text, data = run(), run('--format', 'json')
    assert text.returncode == data.returncode == 0
    names = [t['name'] for t in json.loads(data.stdout)['structure']['types']]
    assert 'Types (6):' in text.stdout
    assert all(f'{n} ' in text.stdout or f'{n}\n' in text.stdout for n in names)
