"""BACK-2483: one stdlib name list, from ``sys.stdlib_module_names`` plus the retired modules.

The hand-typed list (3.8-3.12) lacked ``zoneinfo``, ``ensurepip``, ``opcode`` and others, so a
project file with one of those names was treated as intra-project by ``imports://`` and not flagged
by I004. The list must also keep the modules removed in 3.11-3.13, which reveal still meets in code
written for older Pythons, whichever interpreter runs reveal.
"""

import json
import sys

import pytest
from conftest import _run_reveal_in

from reveal.conventions import PYTHON_STDLIB
from reveal.rules.imports import STDLIB_MODULES

pytestmark = pytest.mark.component

# Removed from the stdlib in 3.11-3.13: absent from sys.stdlib_module_names on a newer interpreter.
REMOVED = ('asyncore', 'asynchat', 'smtpd', 'imp', 'distutils', 'cgi', 'cgitb', 'telnetlib',
           'pipes', 'crypt', 'imghdr', 'aifc', 'audioop', 'msilib', 'lib2to3', 'binhex')
# In the old hand list's blind spot (3.8-3.12 additions and rarely typed names).
NEWLY_RECOGNISED = ('zoneinfo', 'ensurepip', 'opcode', 'pyexpat', 'sre_parse', 'this')


def test_one_list_owns_both_readers():
    assert STDLIB_MODULES is PYTHON_STDLIB


def test_every_interpreter_name_is_stdlib():
    assert set(sys.stdlib_module_names) <= STDLIB_MODULES


@pytest.mark.parametrize('name', REMOVED)
def test_modules_removed_in_newer_pythons_stay_stdlib(name):
    assert name in STDLIB_MODULES


@pytest.mark.parametrize('name', NEWLY_RECOGNISED)
def test_names_missing_from_the_old_hand_list_are_stdlib(name):
    assert name in STDLIB_MODULES


def test_third_party_name_is_not_stdlib():
    assert 'requests' not in STDLIB_MODULES and 'numpy' not in STDLIB_MODULES


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "fx"\nversion = "1"\n', encoding='utf-8')
    for name in NEWLY_RECOGNISED[:3] + ('asyncore',):
        (tmp_path / f'{name}.py').write_text('VALUE = 1\n', encoding='utf-8')
    (tmp_path / 'util.py').write_text('VALUE = 1\n', encoding='utf-8')
    (tmp_path / 'main.py').write_text(
        'import zoneinfo\nimport ensurepip\nimport opcode\nimport asyncore\nimport util\n',
        encoding='utf-8')
    return tmp_path


def test_imports_uri_classifies_shadowed_stdlib_names_as_stdlib(project):
    result = _run_reveal_in(project, 'imports://.', '--format', 'json')
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)['files']['main.py']
    classes = {row['module']: row['classification'] for row in rows}
    assert classes['zoneinfo'] == classes['ensurepip'] == classes['opcode'] == 'stdlib'
    assert classes['asyncore'] == 'stdlib'
    # negative control: a real project module stays intra-project
    assert classes['util'] == 'intra_project'


def test_i004_flags_files_named_like_newly_recognised_stdlib_modules(project):
    result = _run_reveal_in(project, 'check', '.', '--select', 'I004', '--format', 'json')
    flagged = {item['file'] for item in json.loads(result.stdout)['files']
               if item['issues']}
    assert {'zoneinfo.py', 'ensurepip.py', 'opcode.py', 'asyncore.py'} <= flagged
    # negative control: util.py shadows nothing
    assert 'util.py' not in flagged
