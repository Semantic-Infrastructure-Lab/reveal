"""BACK-1231: warnings raised inside pool workers must carry the severity prefix.

The prefix comes from a StreamHandler installed on the 'reveal' logger by
main()'s configure_stderr_logging(). A ProcessPoolExecutor worker never runs
main(), so whether it has that handler depends entirely on the multiprocessing
start method:

  fork       (Linux, CPython <= 3.13)  child inherits it   -> prefixed
  spawn      (macOS, Windows)          child starts clean  -> BARE
  forkserver (CPython 3.14+ on Linux)  child starts clean  -> BARE

A test that runs under the ambient start method passes forever on a fork-default
CI while the bug is live for every macOS user -- which is exactly how the first
BACK-1231 fix shipped green and still reached a reporter. These tests force the
non-fork methods explicitly.
"""

import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.component


_DRIVER = textwrap.dedent("""
    import logging, multiprocessing, os, sys

    if __name__ == '__main__':
        multiprocessing.set_start_method(sys.argv[1], force=True)
        os.environ['REVEAL_DISK_CACHE'] = '0'
        os.environ['REVEAL_MAX_WORKERS'] = '4'

        from reveal.logging_setup import configure_stderr_logging
        configure_stderr_logging()

        from reveal.adapters.imports import ImportsAdapter
        ImportsAdapter(sys.argv[2]).get_structure()
""")


def _corpus_with_parse_failures(tmp_path, n_files=250):
    """A tree big enough to trip the parallel path, full of files that make
    tree-sitter recover from ERROR nodes (which is what emits the warning).

    _PARALLEL_MIN_FILES is 200, so the file count is load-bearing: below it the
    work stays in-process and the bug cannot appear.
    """
    src = tmp_path / 'src'
    src.mkdir()
    for i in range(n_files):
        # Unbalanced braces/parens -> ERROR nodes -> "Partial parse" warning.
        (src / f'broken_{i}.c').write_text(
            f'int f{i}(int a {{ return a + ; \n'
            f'void g{i}(void) {{ if ( \n'
        )
    return src


@pytest.mark.parametrize('start_method', ['spawn', 'forkserver'])
def test_worker_warnings_are_prefixed_under_non_fork_start_methods(tmp_path, start_method):
    if start_method not in __import__('multiprocessing').get_all_start_methods():
        pytest.skip(f'{start_method} unavailable on this platform')

    src = _corpus_with_parse_failures(tmp_path)
    driver = tmp_path / 'driver.py'
    driver.write_text(_DRIVER)

    proc = subprocess.run(
        [sys.executable, str(driver), start_method, str(src)],
        capture_output=True, text=True, timeout=600,
    )

    warning_lines = [
        ln for ln in proc.stderr.splitlines()
        if 'Partial parse' in ln or 'Parse failed' in ln
    ]
    if not warning_lines:
        pytest.skip(
            'no partial-parse warnings emitted -- fixture did not trigger '
            'tree-sitter error recovery on this grammar build'
        )

    unprefixed = [ln for ln in warning_lines if not ln.startswith('WARNING: ')]
    assert not unprefixed, (
        f'{len(unprefixed)} of {len(warning_lines)} worker warnings reached stderr '
        f'without the "WARNING: " prefix under start_method={start_method!r} -- '
        f'the pool initializer is not configuring logging. First: {unprefixed[0]!r}'
    )
