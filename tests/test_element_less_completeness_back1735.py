"""BACK-1735: --decorator-stats read no element but was missing from ELEMENT_LESS_FLAGS.

`reveal a.py b.py --decorator-stats` reported "Decorator Usage in a.py (1 files)" and exited
0: b.py was parsed as the element and dropped (the BACK-1715 class).  Also: the refusal's
`--stdin` hint named `--validate-schema` and `--extract` with no value, which argparse rejects.

Completeness: the early-exit modes in `reveal.main._SPECIAL_MODES` run before any element is
consumed, so a mode whose handler reads the PATH answers for one path and ignores the rest.
The test below runs every such lambda against a recording args object and fails when one
that reads `path` is not declared in ELEMENT_LESS_FLAGS (the next one cannot be missed).
Flags handled outside that table (check, meta, extract, validate-schema, the nginx modes) have
no mechanical marker; they stay declared by hand and are exercised in
test_element_less_flags_back1715.py.
"""

import subprocess
import sys

import pytest

PY = 'def f():\n    return 1\n\n\ndef g():\n    return 2\n'


def _reveal(cwd, *args):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.fixture
def files(tmp_path):
    for name in ('a', 'b'):
        (tmp_path / f'{name}.py').write_text(PY, encoding='utf-8')
    return tmp_path


def test_decorator_stats_refuses_a_second_path(files):
    proc = _reveal(files, 'a.py', 'b.py', '--decorator-stats')
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert 'b.py' in proc.stderr and '--decorator-stats' in proc.stderr
    assert 'Decorator Usage' not in proc.stdout


def test_hint_for_a_flag_that_takes_a_value_names_the_value(files):
    proc = _reveal(files, 'a.py', 'b.py', '--validate-schema', 'beth')
    assert proc.returncode == 2
    assert '--stdin --validate-schema SCHEMA' in proc.stderr
    proc = _reveal(files, 'a.py', 'b.py', '--extract', 'domains')
    assert proc.returncode == 2
    assert '--stdin --extract TYPE' in proc.stderr


def test_hint_for_a_boolean_flag_has_no_placeholder(files):
    proc = _reveal(files, 'a.py', 'b.py', '--meta')
    assert proc.returncode == 2
    assert '--stdin --meta' in proc.stderr
    assert '--meta TYPE' not in proc.stderr and '--meta META' not in proc.stderr


def _special_modes_reading_path(monkeypatch):
    """dest of every _SPECIAL_MODES entry whose handler lambda reads `args.path`."""
    import reveal.main as main_module

    class Probe:
        def __init__(self):
            self.read = set()

        def __getattr__(self, name):
            self.read.add(name)
            return False

    readers = []
    for dest, handler in main_module._SPECIAL_MODES:
        # Stub every module-level function the lambda would call; only attribute reads matter.
        for name in handler.__code__.co_names:
            if callable(handler.__globals__.get(name)):
                monkeypatch.setattr(main_module, name, lambda *a, **k: None)
        probe = Probe()
        handler(probe)
        if 'path' in probe.read:
            readers.append(dest)
    return readers


def test_every_special_mode_that_reads_the_path_is_declared_element_less(monkeypatch):
    from reveal.cli.routing import ELEMENT_LESS_FLAGS
    readers = _special_modes_reading_path(monkeypatch)
    assert readers, 'the probe found no path-reading special mode: it no longer measures anything'
    assert {'explain_file', 'capabilities', 'show_ast', 'decorator_stats'} <= set(readers)
    assert [d for d in readers if d not in ELEMENT_LESS_FLAGS] == []


def test_the_probe_sees_a_missing_declaration(monkeypatch):
    """Negative control: with one declaration removed the check names exactly that mode."""
    readers = _special_modes_reading_path(monkeypatch)
    declared = set(readers) - {'show_ast'}
    assert [d for d in readers if d not in declared] == ['show_ast']


# Negative controls: what must not change.
def test_decorator_stats_on_one_path_still_runs(files):
    proc = _reveal(files, 'a.py', '--decorator-stats')
    assert proc.returncode == 0, proc.stderr
    assert 'Decorator Usage in' in proc.stdout


def test_decorator_stats_on_a_directory_still_runs(files):
    proc = _reveal(files, '.', '--decorator-stats')
    assert proc.returncode == 0, proc.stderr
    assert 'reads no element' not in proc.stderr


def test_a_path_and_an_element_still_work(files):
    proc = _reveal(files, 'a.py', 'f')
    assert proc.returncode == 0, proc.stderr
    assert 'return 1' in proc.stdout
