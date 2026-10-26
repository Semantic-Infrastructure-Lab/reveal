"""An imported function factory (`Fn`) makes `const NAME = Fn(...)` a function (BACK-2178).

BACK-2174 lists a plain-call declarator only when the file calls the name or the callee is a declared
wrapper. three.js declares its shader nodes as `export const x = Fn(...)` and uses them from other files, so
the whole class was dropped. `JS_FUNCTION_FACTORIES` (reveal/conventions.py) names callees that return a
function, keyed by the module they are imported from; a same-spelled callee from anywhere else stays a value.
"""
import json

import pytest

from conftest import _run_reveal_direct

TSL = '''\
import { Fn, vec3 } from '../tsl/TSLBase.js';
import { Fn as Build } from './TSLCore.js';
import { nodeProxy } from 'three/tsl';

function helper(a) { return a; }
export const lit = Fn(([a]) => helper(a));
export const aliased = Build(([a]) => helper(a));
'''
OTHER_MODULE = '''\
import { Fn } from './elsewhere.js';
function helper() { return 1; }
import { derived } from '../tsl/TSLBase.js';

export const notFactory = Fn(() => helper());
export const store = derived(() => helper());
'''
LOCAL_FN = '''\
function Fn(f: () => number) { return 1; }
export const shadow = Fn(() => 1);
'''
BARE = '''\
import { Fn } from 'three/tsl';
export const bare = Fn(() => 1);
'''
FUNCTIONS = {'lit', 'aliased'}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    for name, text in (('tsl.js', TSL), ('other.js', OTHER_MODULE), ('local.ts', LOCAL_FN), ('bare.js', BARE)):
        (root / name).write_text(text, encoding='utf-8')
    return root


def run(*argv):
    out = _run_reveal_direct(*argv, '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def names(path):
    return {f['name'] for f in run(str(path))['structure'].get('functions', [])}


def test_a_factory_imported_from_a_declared_module_is_a_function(project):
    assert FUNCTIONS <= names(project / 'tsl.js')


def test_a_package_specifier_counts_as_a_declared_module(project):
    assert 'bare' in names(project / 'bare.js')


def test_the_same_callee_from_another_module_stays_a_value(project):
    assert not {'notFactory', 'store'} & names(project / 'other.js')


def test_a_locally_declared_callee_of_the_same_name_stays_a_value(project):
    assert 'shadow' not in names(project / 'local.ts')


def test_a_recovered_factory_is_not_reported_as_dropped_and_a_value_is(project):
    meta = run(f'calls://{project}?callers=helper')['meta']
    text = json.dumps(meta.get('warnings', []))
    assert 'function_values_dropped' in text
    assert '"lit"' not in text and 'aliased' not in text
