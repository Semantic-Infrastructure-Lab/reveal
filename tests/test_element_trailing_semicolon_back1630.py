"""BACK-1630: an extracted element's last line was cut at the node's end, so a C/C++
`struct Batch { ... };` printed its last line as `}`. A `;` that is the rest of that
line now belongs to the element; other code after the node on that line does not.
"""

import os
import subprocess
import sys

import pytest

_SOURCE = (
    'struct Batch {\n    int a;\n};\n'
    'struct One { int b; }; int x;\n'
    'class C {\n  int f() { return 1; }\n} ;  \n'
)


def _reveal(cwd, *argv):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', REVEAL_NO_UPDATE_CHECK='1')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.mark.parametrize('name, element, last', [
    ('s.c', 'Batch', '3  };'),
    ('s.cpp', 'Batch', '3  };'),
    ('s.cpp', 'C', '7  } ;'),
    ('s.cpp', 'One', '4  struct One { int b; }'),
])
def test_last_line_keeps_a_closing_semicolon_and_nothing_else(tmp_path, name, element, last):
    (tmp_path / name).write_text(_SOURCE if name.endswith('.cpp') else _SOURCE.split('struct One')[0],
                                 encoding='utf-8')
    run = _reveal(tmp_path, name, element)
    assert run.returncode == 0, run.stderr
    lines = [line.rstrip() for line in run.stdout.splitlines()]
    assert any(line.endswith(last) for line in lines), run.stdout
    assert 'int x' not in run.stdout
