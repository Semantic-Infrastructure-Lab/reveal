"""calls ?callers= and ?rank=callers apply the import bindings callee resolution uses (BACK-2567).

The callers index keys a call by its bare name, so a call through an import from outside the tree
(``json.loads``, ``ts.createProgram``, ``join`` from ``os.path``) was listed as a caller of the
project's same-named function, while ``?callees=`` (BACK-2553) already said it reaches none. Both
directions now read one rule (``analyzers/imports/bindings.reaches``): such a call is no caller of
the project name; a qualified one stays under its own text, a bare one moves under its import's
spelling (``os.path.join``), so ``?rank=callers&builtins=true`` still lists it.

Each test asserts the callers found, not that an answer exists.
"""
from pathlib import Path

from reveal.adapters.calls.adapter import CallsAdapter


def _tree(root: Path, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding='utf-8')
    return str(root)


def _callers(path: str, name: str):
    result = CallsAdapter(path, f'callers={name}').get_structure()
    return sorted((Path(r['file']).name, r['caller'], r.get('call_expr'))
                  for level in result.get('levels') or [] for r in level['callers'])


def _ranked(path: str):
    result = CallsAdapter(path, 'rank=callers&top=0&builtins=true').get_structure()
    return {e['name']: sorted((Path(r['file']).name, r['caller']) for r in e['callers']) for e in result['entries']}


PYTHON = {
    'c.py': 'import json\nfrom os.path import join\n\ndef loads(s):\n    return json.loads(join(s, "x"))\n',
    'd.py': 'def join(a, b):\n    return a\n',
    'e.py': 'from d import join\n\ndef run(s):\n    return join(s, "y")\n',
}


def test_a_call_through_an_external_module_is_no_caller_of_the_project_function(tmp_path):
    # Before: [('c.py', 'loads', 'json.loads')] -- loads "called" itself.
    assert _callers(_tree(tmp_path, PYTHON), 'loads') == []


def test_an_externally_imported_bare_name_is_no_caller_but_an_in_tree_one_is(tmp_path):
    # Before: c.py's `join` (os.path's) was listed beside e.py's (d.py's).
    assert _callers(_tree(tmp_path, PYTHON), 'join') == [('e.py', 'run', 'join')]


def test_the_ranking_moves_them_under_their_import_spelling(tmp_path):
    ranked = _ranked(_tree(tmp_path, PYTHON))
    assert ranked['join'] == [('e.py', 'run')]
    assert ranked['os.path.join'] == [('c.py', 'loads')]
    assert ranked['json.loads'] == [('c.py', 'loads')]
    assert 'loads' not in ranked or ranked['loads'] == []


def test_typescript_namespace_default_and_named_imports(tmp_path):
    path = _tree(tmp_path, {
        'a.ts': ("import ts from 'typescript';\nimport { readFileSync } from 'fs';\n\n"
                 "export function createProgram() {\n  ts.createProgram();\n  readFileSync('x');\n}\n"),
        'b.ts': "export function readFileSync() {}\n",
        'c.ts': "import { readFileSync } from './b';\n\nexport function go() {\n  readFileSync();\n}\n"})
    assert _callers(path, 'createProgram') == []
    assert _callers(path, 'readFileSync') == [('c.ts', 'go', 'readFileSync')]


def test_a_local_definition_shadowing_the_import_is_still_called(tmp_path):
    # Control: the file imports os.path's join and defines its own; a bare join() is its own.
    path = _tree(tmp_path, {'c.py': ('from os.path import join\n\ndef join(a, b):\n    return a\n\n'
                                     'def run(s):\n    return join(s, "x")\n')})
    assert _callers(path, 'join') == [('c.py', 'run', 'join')]


def test_an_unplaced_import_is_a_caller_of_the_definition_at_its_module_path(tmp_path):
    # A namespace package (no __init__.py) the resolution pass cannot place: kept for the definition
    # whose file sits at the module's path, as callee resolution keeps it (BACK-2573).
    path = _tree(tmp_path, {'pyproject.toml': '[project]\nname = "m"\n',
                            'libs/pkg/core.py': 'def run_job(x):\n    return x\n',
                            'libs/pkg/api.py': 'from pkg.core import run_job\n\ndef go(x):\n    return run_job(x)\n'})
    assert _callers(path, 'run_job') == [('api.py', 'go', 'run_job')]


def test_callers_and_the_ranking_agree(tmp_path):
    # The graph invariant callers_view, on this tree: one view of the index for both.
    path = _tree(tmp_path, PYTHON)
    ranked = _ranked(path)
    for name in ('join', 'loads', 'run'):
        assert [(f, c) for f, c, _ in _callers(path, name)] == ranked.get(name, [])
