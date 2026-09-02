"""BACK-1257: --exclude must work on uri:// adapters, not just `check`.

Only overview:// and stats:// ever read a ?exclude= query param (BACK-1042), so
`--exclude` on ast://, calls://, hotspots:// and friends was parsed, warned
about on stderr, and otherwise discarded -- while `reveal check --exclude` on
the same tree filtered correctly. Reported externally after BACK-1249 (which
fixed the *matcher*, not whether it was ever invoked on the URI path).
"""

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path):
    """A tree with a vendored subdir that dominates any complexity ranking."""
    vendor = tmp_path / 'app' / 'assets'
    vendor.mkdir(parents=True)
    core = tmp_path / 'app' / 'models'
    core.mkdir(parents=True)

    def noisy_py(path, name, branches):
        body = '\n'.join(f'    if x == {i}: return {i}' for i in range(branches))
        path.write_text(f'def {name}(x):\n{body}\n    return None\n')

    def noisy_js(path, name, branches):
        body = '\n'.join(f'  if (x === {i}) return {i};' for i in range(branches))
        path.write_text(f'function {name}(x) {{\n{body}\n  return null;\n}}\n')

    for i in range(3):
        noisy_js(vendor / f'bundle_{i}.min.js', f'v{i}', 30)
        noisy_py(vendor / f'lib_{i}.py', f'vendorfn{i}', 30)
    for i in range(2):
        noisy_py(core / f'model_{i}.py', f'corefn{i}', 30)
    return tmp_path


def _query(tree, uri, *flags, key):
    proc = subprocess.run(
        [sys.executable, '-m', 'reveal', uri, *flags, '--format', 'json'],
        capture_output=True, text=True, cwd=str(tree), timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)[key]


def test_ast_honors_exclude(tree):
    """Their row 1: ast:// total_results was 19/19/19 regardless of the flag."""
    baseline = _query(tree, 'ast://.?complexity>3', key='total_results')
    filtered = _query(tree, 'ast://.?complexity>3', '--exclude', 'app/assets/*',
                      key='total_results')
    assert baseline > filtered > 0, (
        f'--exclude did not reduce ast:// results ({baseline} -> {filtered})'
    )


def test_ast_honors_bare_trailing_slash_directory_pattern(tree):
    """BACK-1249's pattern form must work on the URI path too."""
    baseline = _query(tree, 'ast://.?complexity>3', key='total_results')
    filtered = _query(tree, 'ast://.?complexity>3', '--exclude', 'app/assets/',
                      key='total_results')
    assert filtered < baseline


def test_ast_honors_file_shaped_pattern(tree):
    """Directory pruning alone can't do this one -- it needs the yield-site
    check in is_code_file, not just is_skippable_dir."""
    baseline = _query(tree, 'ast://.?complexity>3', key='total_results')
    filtered = _query(tree, 'ast://.?complexity>3', '--exclude', '*.min.js',
                      key='total_results')
    assert filtered < baseline


def test_calls_uncalled_honors_exclude(tree):
    """Their row 3: calls:// total_uncalled was unchanged by the flag."""
    baseline = _query(tree, 'calls://.?uncalled=true&type=function',
                      key='total_uncalled')
    filtered = _query(tree, 'calls://.?uncalled=true&type=function',
                      '--exclude', 'app/assets/*', key='total_uncalled')
    assert baseline > filtered


def test_hotspots_uri_honors_exclude(tree):
    """Their row 2: the top-N stayed entirely inside the excluded directory.

    hotspots:// composes stats:// (file list) and ast:// (function list); the
    former filters via its own ?exclude= param, so both halves need covering.
    """
    out = subprocess.run(
        [sys.executable, '-m', 'reveal', 'hotspots://.?top=5',
         '--exclude', 'app/assets/*', '--format', 'json'],
        capture_output=True, text=True, cwd=str(tree), timeout=600,
    )
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout)
    leaked = [
        e['file'] for e in result['file_hotspots'] + result['function_hotspots']
        if 'app/assets' in e.get('file', '')
    ]
    assert not leaked, f'excluded files still ranked: {leaked}'


def test_hotspots_subcommand_accepts_exclude(tree):
    """The subcommand form used to die with 'unrecognized arguments' while the
    uri:// form accepted the same flag."""
    out = subprocess.run(
        [sys.executable, '-m', 'reveal', 'hotspots', '.', '--exclude', 'app/assets/*'],
        capture_output=True, text=True, cwd=str(tree), timeout=600,
    )
    # Exit code is hotspots' own severity signal (1 == critical hotspots found),
    # so only the parser error and the filtering are asserted here.
    assert 'unrecognized arguments' not in out.stderr, out.stderr
    assert 'app/assets' not in out.stdout, out.stdout


def test_check_subcommand_still_honors_exclude(tree):
    """The one form that already worked must not regress."""
    def files_checked(*flags):
        out = subprocess.run(
            [sys.executable, '-m', 'reveal', 'check', '.', '--exit-zero',
             '--format', 'json', *flags],
            capture_output=True, text=True, cwd=str(tree), timeout=600,
        )
        return json.loads(out.stdout)['summary']['files_checked']

    assert files_checked() > files_checked('--exclude', 'app/assets/*')


def test_scope_does_not_leak_between_dispatches(tree):
    """The walk scope is process-global; a long-lived host (the MCP server)
    must not see one request's --exclude applied to the next."""
    from pathlib import Path

    from reveal.utils.exclusions import (
        active_exclusions, exclusion_scope, path_is_excluded,
    )

    with exclusion_scope(Path(tree), ['app/assets/*']):
        assert path_is_excluded(Path(tree) / 'app' / 'assets' / 'lib_0.py')
    assert active_exclusions() == (None, ())
    assert not path_is_excluded(Path(tree) / 'app' / 'assets' / 'lib_0.py')
