"""C++ call preceded by a bare macro line is a declaration to tree-sitter (BACK-1320).

`CLEAN_PIPES` (no semicolon) then `execvp("ls", nullptr);` parses as the declaration
`CLEAN_PIPES execvp("ls", nullptr);`: a type, then a declarator named `execvp` with an
argument list. No `call_expression` exists, so the call used to vanish with a clean parse.
"""

import pytest

from reveal.adapters.surface import _scan_surface

MACRO_LINE = 'void f() {\n  CLEAN_PIPES\n  execvp("ls", nullptr);\n}\n'


def _entries(code, tmp_path, category='subprocess'):
    path = tmp_path / 'sample.cpp'
    path.write_text(code, encoding='utf-8')
    return _scan_surface(path)['surfaces'][category]


def test_call_after_a_bare_macro_line_is_found(tmp_path):
    entries = _entries(MACRO_LINE, tmp_path)
    assert [(e['name'], e['line']) for e in entries] == [('execvp', 3)]
    assert 'declaration_shaped' not in entries[0]       # macro-like type: a call, not a guess


@pytest.mark.parametrize('body, name', [
    ('CLEAN_PIPES\n  system("ls");', 'system'),
    ('CLEAN_PIPES\n  std::system("ls");', 'std::system'),
    ('Py_BEGIN_ALLOW_THREADS\n  popen("ls", "r");', 'popen'),
    ('CLEAN_PIPES\n  execvp(argv[0], argv);', 'execvp'),       # parses as a function prototype
])
def test_macro_prefixed_call_shapes(body, name, tmp_path):
    entries = _entries(f'void f() {{\n  {body}\n}}\n', tmp_path)
    assert [e['name'] for e in entries] == [name]


def test_a_declaration_shaped_site_with_a_real_type_is_found_but_tagged(tmp_path):
    entries = _entries('void f() {\n  Executor execute(cfg);\n}\n', tmp_path)
    assert [(e['name'], e.get('declaration_shaped')) for e in entries] == [('execute', True)]


@pytest.mark.parametrize('code', [
    'void f() {\n  CLEAN_PIPES\n  std::string s("x");\n  Foo bar("ls");\n}\n',     # names no rule
    'int execvp(const char* path, char* const argv[]);\n',                          # file-scope prototype
    'struct S { CLEAN_PIPES\n  int system(int a); };\n',                            # member prototype
    'CLEAN_PIPES execvp("ls", nullptr);\n',                                        # file scope
    'void f() {\n  int x(5);\n  int system(3);\n}\n',                               # primitive-type variable
])
def test_lookalikes_are_not_calls(code, tmp_path):
    assert _entries(code, tmp_path) == []


def test_a_plain_call_is_unchanged(tmp_path):
    entries = _entries('void f() {\n  execvp("ls", nullptr);\n}\n', tmp_path)
    assert [(e['name'], e['line'], 'declaration_shaped' in e) for e in entries] == [('execvp', 2, False)]
