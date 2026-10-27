"""A call inside an anonymous closure at module level is a call of the module, in Python and PHP too (BACK-2232).

BACK-2191 gave JS/TS this rule: a lambda or closure no listed function, method or class contains is not a
scope anyone reports, so its calls are the module's. Python `register(lambda: helper())` and PHP
`register(function () { return helper(); })` kept the old skip, so `calls ?callers=helper` listed nothing for
them while the same call in JS (and in Ruby, which never skipped blocks) had a `<module>` caller.
A closure inside a listed function stays that function's.
"""
import json
import os

import pytest

from conftest import _run_reveal_direct

SHAPES = {
    'py_register.py': 'register(lambda: helper())\n',
    'py_list.py': 'handlers = [lambda x: helper()]\n',
    'php_closure.php': '<?php\nregister(function () { return helper(); });\n',
    'php_arrow.php': '<?php\nregister(fn() => helper());\n',
    'rb_block.rb': 'register { helper }\n',
}
CONTROLS = {
    'py_plain.py': 'helper()\n',
    'php_plain.php': '<?php\nhelper();\n',
}
OWNED = {
    'py_owned.py': 'def wrapped():\n    return register(lambda: helper())\n',
    'php_owned.php': '<?php\nfunction wrapped() { return register(function () { return helper(); }); }\n',
}
DEFINITIONS = {
    'helper.py': 'def helper():\n    return 1\n',
    'helper.php': '<?php\nfunction helper() { return 1; }\n',
    'helper.rb': 'def helper\n  1\nend\n',
}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    for files in (DEFINITIONS, SHAPES, CONTROLS, OWNED):
        for name, text in files.items():
            (root / name).write_text(text, encoding='utf-8')
    return root


def callers_by_file(root):
    out = _run_reveal_direct(f'calls://{root}?callers=helper', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    found = {}
    for level in json.loads(out.stdout)['levels']:
        for c in level['callers']:
            found.setdefault(os.path.basename(c['file']), set()).add(c['caller'])
    return found


@pytest.mark.parametrize('name', sorted(CONTROLS) + ['rb_block.rb'])
def test_controls_already_have_a_module_caller(project, name):
    assert callers_by_file(project).get(name) == {'<module>'}


@pytest.mark.parametrize('name', sorted(n for n in SHAPES if n != 'rb_block.rb'))
def test_a_module_level_closure_call_has_a_caller(project, name):
    assert callers_by_file(project).get(name) == {'<module>'}


@pytest.mark.parametrize('name,owner', [('py_owned.py', 'wrapped'), ('php_owned.php', 'wrapped')])
def test_a_closure_inside_a_listed_function_stays_that_functions(project, name, owner):
    assert callers_by_file(project).get(name) == {owner}
