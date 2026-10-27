"""reveal run with cwd reveal/adapters on sys.path names the cause (BACK-987).

Five entries of reveal/adapters share a name with a top-level module: ``json``, ``ast``,
``ssl`` and ``trace`` (stdlib) and ``reveal`` (reveal itself). ``python -m`` puts the
current directory first on sys.path, and so does an empty PYTHONPATH entry
(``PYTHONPATH="$X:"``), so from that directory the adapter is imported in the top-level
module's place. Its first relative import failed with "attempted relative import beyond
top-level package", which says nothing about the cause. Renaming the packages moves the
failure rather than ending it (the directory name is the scheme: the registry imports
``reveal.adapters.<scheme>``), so each one refuses to load under a top-level name and
says why. The controls: from any other directory reveal starts, and the inventory test
fails when a new adapter takes a top-level module's name without the guard.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import reveal

ADAPTERS = Path(reveal.__file__).resolve().parent / 'adapters'
PACKAGE_ROOT = ADAPTERS.parent.parent
SHADOWING = ('ast', 'json', 'reveal', 'ssl', 'trace')
GUARD = "if '.' not in __name__:"
DIAGNOSTIC = re.compile(r"was imported as the top-level module '(\w+)': the current directory is "
                        r"reveal/adapters and it is on sys.path")


def _env(pythonpath: str) -> dict:
    env = dict(os.environ)
    env['PYTHONPATH'] = pythonpath
    env['REVEAL_DISK_CACHE'] = '0'
    return env


def _run(args, cwd, pythonpath=str(PACKAGE_ROOT)):
    return subprocess.run([sys.executable, *args], cwd=str(cwd), env=_env(pythonpath),
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


def _source(name: str) -> Path:
    package = ADAPTERS / name / '__init__.py'
    return package if package.exists() else ADAPTERS / f'{name}.py'


def test_python_m_reveal_from_adapters_names_the_cause():
    result = _run(['-m', 'reveal', '--version'], cwd=ADAPTERS)
    assert result.returncode != 0
    assert 'attempted relative import' not in result.stderr
    match = DIAGNOSTIC.search(result.stderr)
    assert match, result.stderr
    assert match.group(1) == 'reveal'


def test_empty_pythonpath_entry_with_a_console_script_names_the_cause(tmp_path):
    # The console script's shape: sys.path[0] is the script's directory, and the empty
    # PYTHONPATH entry (a trailing separator) is what adds the current directory.
    script = tmp_path / 'reveal_console.py'
    script.write_text("import sys\nfrom reveal.main import main\nsys.argv = ['reveal', '--version']\n"
                      "sys.exit(main())\n", encoding='utf-8')
    result = _run([str(script)], cwd=ADAPTERS, pythonpath=f'{PACKAGE_ROOT}{os.pathsep}')
    assert result.returncode != 0
    assert 'attempted relative import' not in result.stderr
    match = DIAGNOSTIC.search(result.stderr)
    assert match, result.stderr
    assert match.group(1) in SHADOWING


@pytest.mark.parametrize('name', SHADOWING)
def test_each_shadowing_adapter_refuses_its_top_level_name(name):
    result = _run(['-c', f'import {name}'], cwd=ADAPTERS)
    assert result.returncode != 0
    match = DIAGNOSTIC.search(result.stderr)
    assert match, result.stderr
    assert match.group(1) == name


def test_reveal_starts_from_any_other_directory():
    with tempfile.TemporaryDirectory() as elsewhere:
        result = _run(['-m', 'reveal', '--version'], cwd=elsewhere,
                      pythonpath=f'{PACKAGE_ROOT}{os.pathsep}')
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith('reveal ')


def test_every_adapter_named_like_a_top_level_module_is_guarded():
    taken = set(sys.stdlib_module_names) | {'reveal'}
    entries = {p.stem for p in ADAPTERS.iterdir()
               if (p.is_dir() and (p / '__init__.py').exists()) or p.suffix == '.py'}
    shadowing = sorted(entries & taken)
    assert shadowing == sorted(SHADOWING)
    unguarded = [name for name in shadowing
                 if GUARD not in _source(name).read_text(encoding='utf-8')]
    assert unguarded == []
