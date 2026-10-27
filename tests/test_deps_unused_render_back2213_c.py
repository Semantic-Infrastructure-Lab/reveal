"""`reveal deps` unused rows: a whole-module import prints its module once.

`import os` was rendered `os.os` (and `import numpy as np` as `numpy.np`, a Go
`"net/http"` as `net/http.http`) because the renderer appended the bound name
the unused analysis reports for whole-module imports. The row now reads the
way `imports://?unused` prints it.
"""

from pathlib import Path

from reveal.rendering.adapters.deps import _render_unused


def _rows(records):
    return [line for line in _render_unused(records, Path('/p'), 10) if '⚠️' in line]


def _rec(module, names, type_, unused_names, alias=None):
    return {'file': '/p/a.py', 'line': 1, 'module': module, 'names': names,
            'type': type_, 'alias': alias, 'unused_names': unused_names}


def test_plain_import_prints_module_once():
    (row,) = _rows([_rec('os', [], 'import', ['os'])])
    assert row.endswith('a.py:1  os')


def test_aliased_and_dotted_imports_print_the_module():
    rows = _rows([_rec('numpy', [], 'import', ['np'], alias='np'),
                  _rec('os.path', [], 'import', ['os'])])
    assert rows[0].endswith('  numpy')
    assert rows[1].endswith('  os.path')


def test_go_and_default_imports_print_the_module():
    rows = _rows([_rec('net/http', ['http'], 'go_import', ['http']),
                  _rec('fs', ['fs'], 'default_import', ['fs'])])
    assert rows[0].endswith('  net/http')
    assert rows[1].endswith('  fs')


def test_partly_used_named_import_names_the_unused_ones():
    (row,) = _rows([_rec('typing', ['Dict', 'List', 'Any'], 'from_import', ['Dict', 'Any'])])
    assert row.endswith('  typing (unused: Dict, Any)')
