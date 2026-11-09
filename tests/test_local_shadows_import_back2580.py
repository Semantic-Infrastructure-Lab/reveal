"""BACK-2580: a parameter or local variable that shadows an imported name is the value, not the import.

The calls gate review found the last real-loss class of the bindings work: Go
``typecheck/subr.go`` ``src.MapType()`` with a ``src *types.Type`` parameter beside
``import "cmd/internal/src"``, and Rust ``iter.next()`` on a ``let`` beside ``use std::iter;``.
The call was read through the import, reached no project definition and was dropped, in both
directions (callees and ``?callers=``). A caller that declares the qualifier itself now calls a
method on that value; a caller that does not still reaches no project definition through the import.
"""

import json
import textwrap

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


def _tree(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding='utf-8')
    return root


def _callees(root, name):
    run = _run_reveal_direct(f'calls://{root.as_posix()}?callees={name}&depth=2', '--format', 'json')
    assert run.returncode == 0, run.stderr
    return {e['call_expr']: e for level in json.loads(run.stdout)['levels'] for e in level['callees']}


def _callers(root, name):
    run = _run_reveal_direct(f'calls://{root.as_posix()}?callers={name}', '--format', 'json')
    assert run.returncode == 0, run.stderr
    return sorted((c['caller'], c['call_expr']) for level in json.loads(run.stdout)['levels']
                  for c in level['callers'])


GO = {
    'types/type.go': '''\
        package types

        type Type struct{ elem *Type }

        func (t *Type) MapType() *Type { return t.elem }
        ''',
    'typecheck/subr.go': '''\
        package typecheck

        import (
        \t"cmd/internal/src"
        \t"example.com/x/types"
        )

        func assignconvfn(src *types.Type, pos src.XPos) *types.Type {
        \treturn src.MapType()
        }

        func viaPackage() *types.Type {
        \treturn src.MapType()
        }
        ''',
}

RUST = {
    'src/lib.rs': '''\
        use std::iter;

        pub struct Walker { items: Vec<u32> }

        impl Walker {
            pub fn next(&mut self) -> Option<u32> { self.items.pop() }
        }

        pub fn drain(w: Walker) -> u32 {
            let mut iter = w;
            let first = iter.next();
            let _ = iter::empty::<u32>();
            first.unwrap_or(0)
        }
        ''',
}

PYTHON = {
    'codec.py': '''\
        def loads(text):
            return text
        ''',
    'use.py': '''\
        import json


        def parse(json, text):
            return json.loads(text)


        def stdlib(text):
            return json.loads(text)
        ''',
}


def test_go_parameter_shadowing_a_package_import(tmp_path):
    root = _tree(tmp_path / 'go', GO)
    edges = _callees(root, 'assignconvfn')
    assert edges['src.MapType']['resolved'] is True
    assert edges['src.MapType']['callee_file'].endswith('types/type.go')
    assert _callers(root, 'MapType') == [('assignconvfn', 'src.MapType')]   # not viaPackage


def test_rust_let_shadowing_a_use(tmp_path):
    root = _tree(tmp_path / 'rs', RUST)
    edges = _callees(root, 'drain')
    assert edges['iter.next']['resolved'] is True
    assert edges['iter::empty']['resolved'] is False      # the module path is still the import's
    assert _callers(root, 'next') == [('drain', 'iter.next')]


def test_python_parameter_shadows_but_the_module_call_stays_external(tmp_path):
    root = _tree(tmp_path / 'py', PYTHON)
    assert _callees(root, 'parse')['json.loads']['resolved'] is True
    assert _callees(root, 'stdlib')['json.loads']['resolved'] is False   # BACK-2553 still holds
    assert _callers(root, 'loads') == [('parse', 'json.loads')]
