"""BACK-2479: ``calls ?callers=NAME`` matches by name, so a name defined in several places merges the
callers of every definition. It said nothing about that. The answer now names each definition, once,
and only when there is more than one (a single definition or a library name needs no note).
"""

import json
import os
import subprocess
import sys

import pytest


def _callers(root, name):
    proc = subprocess.run([sys.executable, '-m', 'reveal', f'calls://{root}?callers={name}', '--format', 'json',
                           '--no-breadcrumbs'], capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _text(root, name):
    proc = subprocess.run([sys.executable, '-m', 'reveal', f'calls://{root}?callers={name}', '--no-breadcrumbs'],
                          capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'a.py').write_text('def process(x):\n    return x\n\ndef only_here(x):\n    return x\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('class Worker:\n    def process(self, x):\n        return x\n', encoding='utf-8')
    (tmp_path / 'c.py').write_text(
        'import json\nfrom a import process, only_here\n\ndef run():\n    process(1)\n    only_here(2)\n    json.loads("1")\n',
        encoding='utf-8')
    return tmp_path


def test_a_name_defined_twice_lists_both_definitions(project):
    data = _callers(project, 'process')
    assert [(os.path.basename(d['file']), d['line']) for d in data['definitions']] == [('a.py', 1), ('b.py', 2)]
    assert data['total_callers'] == 1  # the callers themselves are unchanged


def test_the_text_view_says_the_callers_merge(project):
    out = _text(project, 'process')
    assert 'Defined in: 2 places (' in out and 'a.py:1' in out and 'b.py:2' in out
    assert 'matched by name' in out


def test_a_single_definition_adds_nothing(project):
    assert 'definitions' not in _callers(project, 'only_here')
    assert 'Defined in:' not in _text(project, 'only_here')


def test_a_library_name_with_no_definition_adds_nothing(project):
    data = _callers(project, 'loads')
    assert 'definitions' not in data
    assert 'Defined in:' not in _text(project, 'loads')


def test_an_import_of_the_name_is_not_a_definition(project):
    # c.py imports process and only_here: neither import counts as a second definition
    assert len(_callers(project, 'process')['definitions']) == 2
