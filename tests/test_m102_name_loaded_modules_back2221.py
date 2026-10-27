"""BACK-2221: M102 recognises modules a loader imports by name from a declared table.

reveal/adapters/registry.py lists scheme names in BUILTIN_SCHEMES and imports
``reveal.adapters.<scheme>`` with importlib, so adapters/metrics.py is never named in
an ``import`` statement yet is loaded. The rule reads that declaration (any module
that calls ``import_module(f'<pkg>.{name}')`` and declares a table of bare names), not a
hard-coded file list.
"""
from pathlib import Path

import pytest

from reveal.rules.maintainability.M102 import M102

pytestmark = pytest.mark.component

BODY = "def work():\n    return 1\n"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def project(root, loader):
    write(root / 'pyproject.toml', '[project]\nname="probe"\n')
    write(root / 'pkg' / '__init__.py', '')
    write(root / 'pkg' / 'plugins' / '__init__.py', '')
    write(root / 'pkg' / 'plugins' / 'loader.py', loader)
    for name in ('alpha', 'beta', 'orphan'):
        write(root / 'pkg' / 'plugins' / f'{name}.py', BODY)
    return root / 'pkg' / 'plugins'


def flagged(plugins, name):
    path = plugins / f'{name}.py'
    return [d for d in M102().check(str(path), None, path.read_text(encoding='utf-8'))]


LOADER = '''import importlib

BUILTIN_NAMES = (
    'alpha', 'beta',
)


def load(name):
    if name in BUILTIN_NAMES:
        importlib.import_module(f'pkg.plugins.{name}')
'''


def test_module_listed_in_loader_table_is_not_orphaned(tmp_path):
    plugins = project(tmp_path, LOADER)
    assert flagged(plugins, 'alpha') == []
    assert flagged(plugins, 'beta') == []


def test_unlisted_sibling_is_still_flagged(tmp_path):
    plugins = project(tmp_path, LOADER)
    found = flagged(plugins, 'orphan')
    assert len(found) == 1
    assert 'pkg.plugins.orphan' in found[0].message


def test_table_without_a_name_based_loader_does_not_count(tmp_path):
    """Control: a table of names alone, with no import_module(f'pkg.plugins.{x}'), loads nothing."""
    plugins = project(tmp_path, "BUILTIN_NAMES = ('alpha', 'beta')\n")
    assert len(flagged(plugins, 'alpha')) == 1


def test_loader_prefix_scopes_the_table(tmp_path):
    """Control: the table names modules under the loader's own prefix only."""
    loader = LOADER.replace('pkg.plugins.{name}', 'pkg.other.{name}')
    plugins = project(tmp_path, loader)
    assert len(flagged(plugins, 'alpha')) == 1
