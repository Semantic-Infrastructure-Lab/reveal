"""A call inside an anonymous callback at module level is a call of the module (BACK-2191).

`app.get('/', (req, res) => helper(req))`, `setTimeout(() => helper(2))`, `[1].forEach(function (v) {...})` and
`const x = uniform(1).onUpdate((o) => helper(o))` hold arrows that no function element owns: the call
collector skipped every arrow and function as "its own scope", and nothing listed these as one, so the call to
`helper` had no caller at all (the same on 8406819b). A deferred scope that no listed function, method or class
contains now contributes its calls to `<module>`; one inside a listed function stays that function's.
"""
import json
import os

import pytest

from conftest import _run_reveal_direct

SHAPES = {
    'route.js': "app.get('/', (req, res) => helper(req));\n",
    'timer.js': "setTimeout(() => helper(2), 10);\n",
    'each.js': "[1].forEach(function (v) { helper(v); });\n",
    'mixed.js': "export function other() { return 1; }\nsetTimeout(() => helper(2), 10);\n",
    'member.js': "export const top = uniform(1).onUpdate((o, self) => helper(o));\n",
}
OWNED = '''\
export function wrapped() { return [1].map((v) => helper(v)); }
export const named = (a) => { setTimeout(() => helper(a), 1); };
class K { run() { return [1].map((v) => helper(v)); } }
'''
DEFINITION = 'export function helper(x) { return x; }\n'


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'helper.js').write_text(DEFINITION, encoding='utf-8')
    for name, text in SHAPES.items():
        (root / name).write_text(text, encoding='utf-8')
    (root / 'owned.js').write_text(OWNED, encoding='utf-8')
    return root


def callers_by_file(root):
    out = _run_reveal_direct(f'calls://{root}?callers=helper', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    found = {}
    for level in json.loads(out.stdout)['levels']:
        for c in level['callers']:
            found.setdefault(os.path.basename(c['file']), set()).add(c['caller'])
    return found


@pytest.mark.parametrize('name', sorted(SHAPES))
def test_a_module_level_callback_call_has_a_caller(project, name):
    assert callers_by_file(project).get(name) == {'<module>'}


def test_a_callback_inside_a_listed_function_stays_that_functions(project):
    assert callers_by_file(project)['owned.js'] == {'wrapped', 'named', 'run'}
