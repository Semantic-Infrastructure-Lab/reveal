"""BACK-1774: a reader that closed early (`reveal FILE --show-ast | head`) must not leave noise.

BACK-1767 made the special modes flush inside the BrokenPipe handler of main._dispatch_and_run;
BACK-1774 asked whether the file views (--show-ast, --capabilities, --explain-file,
--decorator-stats, the outline, the directory tree) needed the same. They go through the same
seam, so this pins it for each: the reader is closed before the child writes, which makes the
failure deterministic where `| head -c 1` races the writer.

On the tree before BACK-1767, this harness reported "Exception ignored ... BrokenPipeError"
(exit 120) for --capabilities, --explain-file, --decorator-stats, --agent-help and
--list-supported; --show-ast was already quiet there because its output is larger than the pipe
buffer and raised inside the handler.
"""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX pipe semantics')

# Enough text for --show-ast and the outline to exceed one pipe buffer's worth of lines.
PY = ''.join(f'def f{i}(a, b):\n    return a + b + {i}\n\n\n' for i in range(40))


def _closed_pipe_run(command, cwd=None):
    """Run ``command`` with its stdout read end already closed; return (exit code, stderr)."""
    proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdout.close()
    try:
        err = proc.stderr.read()
        code = proc.wait(timeout=60)
    finally:
        proc.stderr.close()
        if proc.poll() is None:
            proc.kill()
    return code, err.decode('utf-8', errors='replace')


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.py').write_text(PY, encoding='utf-8')
    (tmp_path / 'a.md').write_text('# A\n\ntext\n\n## B\n\nbody\n', encoding='utf-8')
    return tmp_path


MODES = [
    ['a.py', '--show-ast'], ['a.py', '--capabilities'], ['a.py', '--explain-file'],
    ['.', '--decorator-stats'], ['a.py'], ['a.py', '--format', 'json'], ['a.py', '--outline'],
    ['a.md', '--section', 'B'], ['.'], ['--rules'], ['--discover'], ['--agent-help'],
    ['--list-supported'],
]


@pytest.mark.parametrize('argv', MODES, ids=[' '.join(m) for m in MODES])
def test_a_closed_pipe_is_quiet(tree, argv):
    code, err = _closed_pipe_run([sys.executable, '-m', 'reveal', *argv], tree)
    assert 'BrokenPipeError' not in err and 'Exception ignored' not in err, err
    assert code == 0, (code, err)


def test_the_harness_detects_the_noise_it_guards_against():
    """Negative control: a bare interpreter writing into the same closed pipe is reported."""
    code, err = _closed_pipe_run([sys.executable, '-c', 'print("x" * 100)'])
    assert 'BrokenPipeError' in err and code == 120, (code, err)


def test_a_fully_read_pipe_still_carries_the_output(tree):
    proc = subprocess.run([sys.executable, '-m', 'reveal', 'a.py', '--show-ast'], cwd=tree,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert proc.returncode == 0 and 'function_definition' in proc.stdout, proc.stderr
