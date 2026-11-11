"""Parameter names come from syntax facts, never display signatures."""
import pytest

from reveal.api import query
from reveal.registry import get_analyzer

CASES = {
    'py': ('def sink(a, sep=",", /, *args, option=")", **kwargs): return a\n', ['a', 'sep', 'args', 'option', 'kwargs']),
    'js': ('function sink(a, sep=",") { return a; }\n', ['a', 'sep']),
    'ts': ('function sink(a: number, sep: string=","): number { return a; }\n', ['a', 'sep']),
    'tsx': ('function sink(a: number, sep: string=","): number { return a; }\n', ['a', 'sep']),
    'go': ('package p\nfunc sink(a, b int, rest ...string) int { return a }\n', ['a', 'b', 'rest']),
    'rs': ('fn sink(a: i32, sep: &str) -> i32 { a }\n', ['a', 'sep']),
    'java': ('class A { int sink(int a, String sep) { return a; } }\n', ['a', 'sep']),
    'cs': ('class A { int sink(int a, string sep=",") { return a; } }\n', ['a', 'sep']),
    'php': ('<?php function sink($a, $sep=",") { return $a; }\n', ['$a', '$sep']),
    'rb': ('def sink(a, sep=",")\n a\nend\n', ['a', 'sep']),
    'c': ('int sink(int a, const char *sep) { return a; }\n', ['a', 'sep']),
    'cpp': ('int sink(int a, const char *sep=",") { return a; }\n', ['a', 'sep']),
}


@pytest.mark.parametrize('extension', CASES)
def test_native_names_survive_structure_and_calls_detail(tmp_path, extension):
    source, expected = CASES[extension]
    path = tmp_path / ('app.' + extension)
    path.write_text(source, encoding='utf-8')
    structure = get_analyzer(str(path))(str(path)).get_structure()
    functions = structure.get('functions', [])
    sink = next(f for f in functions if f['name'].split('.')[-1] == 'sink')
    assert sink['parameters'] == expected
    answer = query(f'calls://{tmp_path.as_posix()}?callees=sink&detail')
    assert answer['definitions'][0]['params'] == expected


def test_display_signature_is_not_a_parameter_source():
    from reveal.adapters.calls.index import CalleeSource, walk_callees
    structures = [{'file': 'app.py', 'elements': [{'name': 'sink', 'line': 1, 'category': 'functions',
                    'signature': '(invented, phantom)', 'parameters': ['real'], 'calls': []}]}]
    source = CalleeSource.from_structures(structures)
    assert walk_callees('.', 'sink', source=source).roots[0].params == ['real']


def test_unqualified_legacy_structure_declines_instead_of_guessing():
    from reveal.adapters.calls.index import CalleeSource, walk_callees
    structures = [{'file': 'app.unknown', 'elements': [{'name': 'sink', 'line': 1, 'category': 'functions',
                    'signature': '(invented, phantom)', 'calls': []}]}]
    source = CalleeSource.from_structures(structures)
    assert walk_callees('.', 'sink', source=source).roots[0].params is None


@pytest.mark.parametrize('extension,source,expected', [
    ('py', 'class A:\n def sink(self, x: dict[str, str] = {"a,b": ")"}, *, y=","): return x\n', ['x', 'y']),
    ('js', 'const sink = ({x, a: renamed, y=","}, [first, ...rest], ...args) => x;\n',
     ['x', 'renamed', 'y', 'first', 'rest', 'args']),
    ('ts', 'const sink = (a?: string, ...rest: string[]) => a;\n', ['a', 'rest']),
    ('go', 'package p\ntype A struct {}\nfunc (a A) sink(x int) (int, error) { return x, nil }\n', ['x']),
    ('rs', 'struct A; impl A { fn sink(&self, mut x: i32) -> i32 { x } }\n', ['x']),
    ('java', 'class A { void sink(String... args) {} }\n', ['args']),
    ('rb', 'def sink(a, key: ",", *rest, **kwargs, &block)\n a\nend\n', ['a', 'key', 'rest', 'kwargs', 'block']),
    ('c', 'int sink(void) { return 1; }\n', []),
    ('c', 'int sink(int (*cb)(int), int a) { return cb(a); }\n', ['cb', 'a']),
])
def test_receiver_variadic_and_pattern_names(tmp_path, extension, source, expected):
    (tmp_path / ('app.' + extension)).write_text(source, encoding='utf-8')
    answer = query(f'calls://{tmp_path.as_posix()}?callees=sink&detail')
    assert answer['definitions'][0]['params'] == expected


def test_unqualified_language_and_binding_shape_are_explicitly_unavailable(tmp_path, capsys):
    from reveal.core.parameters import parameter_names
    assert parameter_names(None, 'unknown', lambda n: '') is None
    (tmp_path / 'app.kt').write_text('fun sink(a: String) = a\n', encoding='utf-8')
    answer = query(f'calls://{tmp_path.as_posix()}?callees=sink&detail')
    assert answer['definitions'][0]['params'] is None
    from reveal.adapters.calls.renderer import render_calls_structure
    render_calls_structure(answer, 'text')
    text = capsys.readouterr().out
    assert 'params: unavailable' in text


def test_trace_accepts_explicitly_unavailable_parameters_but_not_a_missing_field():
    from reveal.adapters.trace import _trace_frame_valid
    frame = {'name': 'f', 'file': 'a.kt', 'line': 1, 'depth': 0, 'resolved': True,
             'ambiguous': False, 'params': None, 'effects': [], 'calls': []}
    assert _trace_frame_valid(frame, 1)
    del frame['params']
    assert not _trace_frame_valid(frame, 1)
