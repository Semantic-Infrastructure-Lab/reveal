"""BACK-1606: flags and params the help documents must do something, or not be documented.

Each test here failed on the code before the fix: the flag or param was advertised
and then ignored (with a note at best, silently at worst).
"""

import os
import subprocess
import sys
from argparse import Namespace

import pytest

from reveal.adapters.architecture import ArchitectureRenderer
from reveal.adapters.deps import DepsAdapter, DepsRenderer
from reveal.adapters.overview import OverviewRenderer
from reveal.cli.routing.uri import _render_structure_top_kwargs


def _cli(*argv, cwd):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


@pytest.fixture
def pkg(tmp_path):
    """Three modules with different import counts, so 'Top importers' has three rows."""
    root = tmp_path / 'pkg'
    root.mkdir()
    (root / 'a.py').write_text('import os\nimport sys\nimport json\n', encoding='utf-8')
    (root / 'b.py').write_text('import os\nimport sys\n', encoding='utf-8')
    (root / 'c.py').write_text('import os\n', encoding='utf-8')
    return tmp_path


# --- (2) deps://?top=N, and the same seam for overview:// and architecture:// -------------

@pytest.mark.parametrize('renderer', [DepsRenderer, OverviewRenderer, ArchitectureRenderer])
def test_query_top_reaches_the_renderer(tmp_path, renderer):
    adapter = DepsAdapter(str(tmp_path), 'top=3')
    assert _render_structure_top_kwargs(renderer, Namespace(), adapter) == {'top': 3}


def test_no_query_top_leaves_the_renderer_default(tmp_path):
    assert _render_structure_top_kwargs(DepsRenderer, Namespace(), DepsAdapter(str(tmp_path))) == {}


def test_all_still_wins_over_query_top(tmp_path):
    kwargs = _render_structure_top_kwargs(DepsRenderer, Namespace(all=True, verbose=False),
                                          DepsAdapter(str(tmp_path), 'top=1'))
    assert kwargs['top'] >= 10**6


def test_deps_uri_top_caps_each_section_with_no_note(pkg):
    run = _cli('deps://pkg?top=1', cwd=pkg)
    assert run.returncode in (0, 1), run.stderr
    assert 'no effect' not in run.stderr
    importers = run.stdout.split('Top importers', 1)[1].split('Next steps', 1)[0]
    assert sum('.py' in line for line in importers.splitlines()) == 1


# --- (4) reveal PATH --check runs under the flag ledger ------------------------------------

def test_outline_with_check_is_named(pkg):
    run = _cli('pkg/a.py', '--outline', '--check', cwd=pkg)
    assert 'Note: --outline has no effect on --check' in run.stderr


def test_check_alone_gets_no_note(pkg):
    run = _cli('pkg/a.py', '--check', cwd=pkg)
    assert 'no effect' not in run.stderr


def test_help_no_longer_teaches_outline_with_check(pkg):
    assert '--outline --check' not in _cli('--help', cwd=pkg).stdout


# --- (1) reveal check --only-failures / --advanced -----------------------------------------

def test_check_help_does_not_advertise_its_no_op_flags(pkg):
    out = _cli('check', '--help', cwd=pkg).stdout
    assert '--only-failures' not in out and '--advanced' not in out


def test_check_still_accepts_them_and_names_them(pkg):
    run = _cli('check', 'pkg/a.py', '--only-failures', '--advanced', cwd=pkg)
    assert run.returncode != 2, run.stderr
    assert "--only-failures, --advanced has no effect on 'reveal check'" in run.stderr
