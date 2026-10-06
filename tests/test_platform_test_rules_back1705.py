"""BACK-1705: V036 (fork-dependent tests) and V037 (POSIX-only calls without a Windows guard).

Both scan the dev checkout's tests/ from ``reveal reveal:// --check``. Each test below builds
a fake checkout (pyproject.toml, reveal/{analyzers,rules}/, tests/) and points the rules at it
with REVEAL_DEV_ROOT, so nothing is patched. PRE_991424A3 is the module-level shape of
tests/test_check_lost_worker_back1681.py before 991424a3 (the test that went red on py3.14
Linux and macOS): V036 must flag it and must pass the 991424a3 version.
"""

import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.adapters.reveal.operations import check
from reveal.rules.validation.V036 import V036
from reveal.rules.validation.V037 import V037

pytestmark = pytest.mark.component

PRE_991424A3 = '''
import os
import sys
from pathlib import Path

import pytest

from reveal.cli import file_checker
from reveal.cli.file_checker import handle_recursive_check

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or "fork" not in __import__("multiprocessing").get_all_start_methods(),
    reason="the dying worker is injected by patching the module the forked pool inherits",
)


def _killer(real, victim):
    def check(file_path, *args, **kwargs):
        if Path(file_path).name == victim:
            os._exit(1)
        return real(file_path, *args, **kwargs)
    return check


@pytest.fixture
def two_workers(monkeypatch):
    monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")


def test_text_path_counts_every_file_when_a_worker_dies(tmp_path, monkeypatch, two_workers):
    monkeypatch.setattr(file_checker, "check_and_collect_file",
                        _killer(file_checker.check_and_collect_file, "m2.py"))
    file_checker._check_text([], tmp_path, ["B001"], None)


def test_a_pool_that_cannot_start_falls_back_to_serial(tmp_path, monkeypatch, two_workers):
    monkeypatch.setattr(file_checker, "ProcessPoolExecutor", None)
'''

AT_991424A3 = PRE_991424A3.replace(
    'def test_text_path_counts',
    'needs_forked_workers = pytest.mark.skipif(\n'
    '    multiprocessing.get_context().get_start_method() != "fork", reason="")\n\n\n'
    '@needs_forked_workers\ndef test_text_path_counts')


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A fake dev checkout the V-rules resolve through REVEAL_DEV_ROOT; returns a writer
    for tests/<name> (dedented)."""
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
    for sub in ('analyzers', 'rules'):
        (tmp_path / 'reveal' / sub).mkdir(parents=True)
    (tmp_path / 'tests').mkdir()
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(tmp_path / 'reveal'))

    def write(name, source):
        path = tmp_path / 'tests' / name
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return path
    return write


def _run(rule_class):
    rule = rule_class()
    return rule, rule.check('reveal://', None, '')


def _lines(detections):
    return sorted((d.file_path, d.line) for d in detections)


# ── V036 ────────────────────────────────────────────────────────────────────────


class TestV036:
    def test_attributes(self):
        rule = V036()
        assert (rule.code, rule.internal, rule.uri_patterns) == ('V036', True, ['^reveal://.*'])

    def test_ignores_a_regular_file(self):
        assert V036().check('tests/test_x.py', None, PRE_991424A3) == []

    def test_flags_the_test_991424a3_fixed(self, checkout):
        """Positive control: fork *availability* is not a guard; the dying worker is."""
        path = checkout('test_check_lost_worker_back1681.py', PRE_991424A3)
        source_lines = path.read_text(encoding='utf-8').splitlines()
        exit_line = source_lines.index('            os._exit(1)') + 1
        _, found = _run(V036)
        assert _lines(found) == [('tests/test_check_lost_worker_back1681.py', exit_line)]
        assert 'os._exit()' in found[0].message
        assert found[0].context == 'os._exit(1)'

    def test_passes_the_991424a3_version(self, checkout):
        checkout('test_check_lost_worker_back1681.py', AT_991424A3)
        assert _run(V036)[1] == []

    @pytest.mark.parametrize('guard', [
        'from conftest import needs_forked_workers',
        'FORKS = multiprocessing.get_start_method() == "fork"',
        'CTX = multiprocessing.get_context("fork")',
        'pool = ProcessPoolExecutor(mp_context=CTX)',
    ])
    def test_any_start_method_guard_passes(self, checkout, guard):
        checkout('test_x.py', PRE_991424A3 + '\n' + guard + '\n')
        assert _run(V036)[1] == []

    def test_reports_the_injection_next_to_its_pool(self, checkout):
        checkout('test_x.py', '''
            from unittest.mock import patch
            import pytest

            def test_unrelated():
                with patch('reveal.a.b'):
                    pass

            @pytest.mark.real_worker_pool
            def test_counts_worker_builds(monkeypatch):
                monkeypatch.setattr(mod, "build", counting)
        ''')
        assert _lines(_run(V036)[1]) == [('tests/test_x.py', 11)]

    @pytest.mark.parametrize('source', [
        # a patch, but the pool stays serial (the suite's REVEAL_MAX_WORKERS=1)
        'def test(monkeypatch):\n    monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")\n'
        '    monkeypatch.setattr(m, "f", g)\n',
        # a pool, but the patch is the pool constructor (acts in the parent)
        'def test(monkeypatch):\n    monkeypatch.setenv("REVEAL_MAX_WORKERS", "5")\n'
        '    with patch.object(file_checker, "ProcessPoolExecutor", side_effect=spy):\n'
        '        pass\n',
        # the pool runs in a subprocess; os._exit is in the driver's source string
        'DRIVER = "import os; os._exit(1)"\n'
        'def test(monkeypatch):\n    monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")\n',
        # environment patches reach spawned workers too
        'def test(monkeypatch):\n    monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")\n'
        '    monkeypatch.setenv("X", "1")\n',
    ])
    def test_negative_controls(self, checkout, source):
        checkout('test_x.py', source)
        assert _run(V036)[1] == []

    def test_noqa_on_the_reported_line(self, checkout):
        checkout('test_x.py', PRE_991424A3.replace(
            'os._exit(1)', 'os._exit(1)  # noqa: V036 reviewed: runs under fork only'))
        assert _run(V036)[1] == []


# ── V037 ────────────────────────────────────────────────────────────────────────


class TestV037:
    def test_attributes(self):
        rule = V037()
        assert (rule.code, rule.internal, rule.uri_patterns) == ('V037', True, ['^reveal://.*'])

    def test_ignores_a_regular_file(self):
        assert V037().check('tests/test_x.py', None, 'os.fork()') == []

    def test_flags_each_posix_only_use(self, checkout):
        checkout('test_x.py', '''
            import fcntl
            import os
            import signal
            from pathlib import Path

            def test_it(proc):
                os.kill(proc.pid, signal.SIGKILL)
                assert os.getuid() != 0
                pid = os.fork()
                open('/tmp/out.txt', 'w').write('x')
                Path('/tmp/d').mkdir()
                subprocess.run(['ls'], cwd='/tmp', timeout=5)
                open(f'/proc/{pid}/stat', encoding='utf-8')
        ''')
        _, found = _run(V037)
        assert [d.line for d in found] == [2, 8, 9, 10, 11, 12, 13, 14]
        assert {d.file_path for d in found} == {'tests/test_x.py'}
        assert 'signal.SIGKILL' in found[1].message

    @pytest.mark.parametrize('guard', [
        "pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX')",
        "SKIP = sys.platform.startswith('win')",
        "POSIX = os.name != 'nt'",
        "HAS_FORK = hasattr(os, 'fork')",
        "fcntl = pytest.importorskip('fcntl')",
    ])
    def test_a_windows_guard_passes(self, checkout, guard):
        checkout('test_x.py', f'{guard}\n\ndef test(p):\n    os.kill(p, signal.SIGKILL)\n')
        assert _run(V037)[1] == []

    @pytest.mark.parametrize('source', [
        # cross-platform names
        'def test(p):\n    os.kill(p, signal.SIGTERM)\n    os.getpid()\n    os._exit(0)\n',
        # POSIX paths as strings only (a fake root, an expected value)
        "def test():\n    run(Path('/tmp'))\n    assert x == '/tmp/a.py'\n",
        # POSIX calls inside a source fixture / subprocess driver
        "SRC = '''\nimport fcntl\nos.fork()\nopen('/tmp/x', 'w')\n'''\n",
        # tempfile, not /tmp
        "def test(tmp_path):\n    open(tmp_path / 'x', 'w')\n",
    ])
    def test_negative_controls(self, checkout, source):
        checkout('test_x.py', source)
        assert _run(V037)[1] == []

    def test_noqa_on_the_reported_line(self, checkout):
        checkout('test_x.py', 'def test(p):\n    os.kill(p, signal.SIGKILL)  # noqa: V037 why\n'
                              '    os.fork()\n')
        assert _lines(_run(V037)[1]) == [('tests/test_x.py', 3)]

    def test_the_pre_991424a3_test_is_not_a_v037_case(self, checkout):
        """It already skipped win32, and os._exit exists on Windows: its failure was the
        start method (V036), not the platform."""
        checkout('test_check_lost_worker_back1681.py', PRE_991424A3)
        assert _run(V037)[1] == []


# ── shared scope and prerequisites ──────────────────────────────────────────────


BAD = {V036: PRE_991424A3, V037: 'import fcntl\n'}


@pytest.mark.parametrize('rule_class', [V036, V037])
class TestScope:
    def test_scans_test_modules_and_conftest_only(self, checkout, rule_class):
        (Path(checkout('test_a.py', '')).parent / 'fixtures').mkdir()
        checkout('helper_fixture.py', BAD[rule_class])
        checkout('fixtures/sample.py', BAD[rule_class])
        checkout('fixtures/test_nested.py', BAD[rule_class])  # nested test modules count
        checkout('conftest.py', BAD[rule_class])
        _, found = _run(rule_class)
        assert {d.file_path for d in found} == {
            'tests/fixtures/test_nested.py', 'tests/conftest.py'}

    def test_unparseable_module_is_disclosed_not_skipped(self, checkout, rule_class):
        checkout('test_broken.py',
                 'import fcntl\nos.fork(\nmonkeypatch.setattr(ProcessPoolExecutor\n')
        rule, found = _run(rule_class)
        assert found == []
        assert [(o['status'], o['subject']) for o in rule.outcomes] == [
            ('unavailable', 'tests/test_broken.py')]

    def test_installed_package_is_not_applicable(self, tmp_path, monkeypatch, rule_class):
        root = tmp_path / 'site' / 'reveal'
        for sub in ('analyzers', 'rules'):
            (root / sub).mkdir(parents=True)
        monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
        rule, found = _run(rule_class)
        assert found == [] and [o['status'] for o in rule.outcomes] == ['skipped']


def test_reveal_own_tests_are_clean(monkeypatch):
    """The rules hold on this checkout's tests/ (what CI's `reveal reveal:// --check` runs)."""
    root = Path(reveal.__file__).parent
    if not (root.parent / 'tests').is_dir():
        pytest.skip('installed package, no tests/')
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    result = check(select=['V036', 'V037'])
    assert result['detections'] == []
    assert {e['rule']: e['status'] for e in result['coverage']['rules']} == {
        'V036': 'run', 'V037': 'run'}
