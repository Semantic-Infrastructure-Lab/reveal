"""BACK-1066: I001 and imports://?unused share one definition of "unused".

They used to disagree in both directions: the adapter missed the unused names of a
partly-used `from x import a, b`, ignored `eslint-disable`, and skipped
`# type: ignore`; I001 flagged a used `import * as fs from 'fs'`. The parity test
runs both over the same files, so a future divergence fails here.
"""

import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.rules.imports.I001 import I001

FILES = {
    'a.js': (
        "import * as fs from 'fs';\n"
        "import * as path from 'path';\n"
        "import { a, b, c } from './x';\n"
        "import d from './d'; // eslint-disable-line no-unused-vars\n"
        "console.log(fs.readFileSync, a);\n"
    ),
    'a.py': (
        "import os, sys\n"
        "from typing import List, Dict, Any\n"
        "from foo import bar as baz, qux  # noqa: F401\n"
        "import json  # type: ignore\n"
        "x: List[int] = [os.sep]\n"
    ),
    'a.go': (
        'package p\n\nimport (\n\t"fmt"\n\t"os"\n\t_ "embed"\n)\n\nfunc f() { fmt.Println() }\n'
    ),
    'a.rs': "use std::io;\nuse std::fmt::{self, Display};\nfn f(_: &dyn Display) {}\n",
    # BACK-1467: stubs are analyzed; `X as X` is a PEP 484 re-export, a plain import is private
    'a.pyi': (
        "from typing import Any\n"
        "from .core import Engine as Engine, Helper\n"
        "import os as os\n"
        "import sys\n"
        "x: Any\n"
    ),
}


def _i001_lines(path):
    detections = I001().check(str(path), None, path.read_text())
    return sorted({d.line for d in detections})


def _adapter(path):
    return ImportsAdapter(str(path), 'unused').get_structure()


@pytest.fixture
def tree(tmp_path):
    for name, code in FILES.items():
        (tmp_path / name).write_text(code, encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('name', sorted(FILES))
def test_rule_and_adapter_flag_the_same_lines(tree, name):
    path = tree / name
    adapter_lines = sorted({u['line'] for u in _adapter(path)['unused']})
    assert adapter_lines == _i001_lines(path)


def test_partly_used_from_import_reports_only_the_unused_names(tree):
    unused = {u['line']: u['unused_names'] for u in _adapter(tree / 'a.py')['unused']}
    assert unused[2] == ['Dict', 'Any']
    assert 3 not in unused          # `# noqa: F401`


def test_type_ignore_is_not_a_suppression(tree):
    # the adapter used to skip it, I001 never did; `import json` is unused
    assert 4 in {u['line'] for u in _adapter(tree / 'a.py')['unused']}


def test_used_namespace_import_is_not_flagged_but_unused_one_is(tree):
    lines = _i001_lines(tree / 'a.js')
    assert 1 not in lines           # fs.readFileSync is used
    assert 2 in lines               # path is not
    assert {u['line'] for u in _adapter(tree / 'a.js')['unused']} == {2, 3}


def test_eslint_disable_suppresses_in_both(tree):
    assert 4 not in _i001_lines(tree / 'a.js')
    assert 4 not in {u['line'] for u in _adapter(tree / 'a.js')['unused']}


def test_redundant_alias_is_a_reexport_not_unused(tree):
    unused = {u['line']: u['unused_names'] for u in _adapter(tree / 'a.pyi')['unused']}
    assert unused[2] == ['Helper']  # `Engine as Engine` re-exports, Helper is private
    assert 3 not in unused          # `import os as os`
    assert 4 in unused              # `import sys`
    assert (tree / 'a.pyi').exists() and _i001_lines(tree / 'a.pyi') == [2, 4]


def test_redundant_alias_in_a_py_module_is_a_reexport(tmp_path):
    path = tmp_path / 'm.py'
    path.write_text("from .core import Engine as Engine\nimport os as os\n", encoding='utf-8')
    assert _i001_lines(path) == []


def test_init_stub_is_skipped_like_init_module(tmp_path):
    path = tmp_path / '__init__.pyi'
    path.write_text("import sys\n", encoding='utf-8')
    assert _i001_lines(path) == []
