"""BACK-1720: V038 (raw subprocess bytes asserted on newlines without normalising).

Same fake-checkout harness as tests/test_platform_test_rules_back1705.py. PRE_79A576C9 is
the module-level shape of tests/test_crlf_sources_back1706.py before 79a576c9 (red on all
three Windows jobs): V038 must flag it and pass the 79a576c9 version.
"""

import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.adapters.reveal.operations import check
from reveal.rules.validation.V038 import V038

pytestmark = pytest.mark.component

PRE_79A576C9 = '''
import os
import subprocess
import sys


def _reveal(cwd, *args):
    return subprocess.run(
        [sys.executable, '-m', 'reveal', *args], cwd=str(cwd),
        capture_output=True, timeout=120,
    )


def _both(tmp_path, name, *args):
    out = {}
    for label in ('lf', 'crlf'):
        r = _reveal(tmp_path / label, name, *args)
        assert r.returncode in (0, 1), r.stderr.decode('utf-8', 'replace')
        assert b'\\r' not in r.stdout, f'{label}: stray CR in stdout for {args}'
        assert b'\\r' not in r.stderr, f'{label}: stray CR in stderr for {args}'
        out[label] = r.stdout.decode('utf-8')
    return out
'''

AT_79A576C9 = PRE_79A576C9.replace(
    "        assert b'\\r' not in r.stdout,",
    "        stdout = _own_newlines(r.stdout)\n        assert b'\\r' not in stdout,").replace(
    "def _both(", '''def _own_newlines(data):
    return data.replace(b'\\r\\n', b'\\n') if sys.platform == 'win32' else data


def _both(''')


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


def _run():
    rule = V038()
    return rule, rule.check('reveal://', None, '')


def _lines(detections):
    return sorted((d.file_path, d.line) for d in detections)


def _module(body):
    """A test module whose helper runs a byte-mode subprocess, then *body* (dedented)."""
    return ('import subprocess\nimport sys\n\n\n'
            'def run(*a):\n    return subprocess.run(a, capture_output=True, timeout=60)\n\n\n'
            + textwrap.dedent(body))


class TestV038:
    def test_attributes(self):
        rule = V038()
        assert (rule.code, rule.internal, rule.uri_patterns) == ('V038', True, ['^reveal://.*'])

    def test_ignores_a_regular_file(self):
        assert V038().check('tests/test_x.py', None, PRE_79A576C9) == []

    def test_flags_the_test_79a576c9_fixed(self, checkout):
        """Positive control: both stray-CR assertions of BACK-1706's original helper."""
        path = checkout('test_crlf_sources_back1706.py', PRE_79A576C9)
        lines = path.read_text(encoding='utf-8').splitlines()
        stdout_line = next(i for i, ln in enumerate(lines, 1) if 'r.stdout,' in ln)
        _, found = _run()
        assert _lines(found) == [('tests/test_crlf_sources_back1706.py', stdout_line),
                                 ('tests/test_crlf_sources_back1706.py', stdout_line + 1)]
        assert "b'\\r'" in found[0].message
        assert found[0].context.startswith("assert b'\\r' not in r.stdout")

    def test_passes_the_79a576c9_version(self, checkout):
        checkout('test_crlf_sources_back1706.py', AT_79A576C9)
        assert _run()[1] == []

    @pytest.mark.parametrize('body', [
        "def test(): assert run('x').stdout == b'a\\r\\n'\n",
        "def test(): assert run('x').stdout.count(b'\\n') == 3\n",
        "def test(): assert run('x').stdout.split(b'\\n')[0] == b'a'\n",
        "def test(): assert run('x').stdout.startswith(b'a\\n')\n",
        "def test(): assert run('x').stdout.splitlines(True)\n",
        "def test(): assert run('x').stdout.splitlines(keepends=True)\n",
        "def test(): assert b'a\\nb' in run('x').stdout\n",
        # through a name assigned from the call, and from .stderr
        "def test():\n    r = run('x')\n    out = r.stdout\n    assert b'\\r' not in out\n",
        "def test():\n    p = subprocess.Popen(['x'], stderr=subprocess.PIPE)\n"
        "    _, err = p.communicate()\n    assert err == b'x\\n'\n"
        "    assert b'\\r' not in p.stderr.read()\n",
        "def test(): assert subprocess.check_output(['x']) == b'ok\\n'\n",
    ])
    def test_flags_each_newline_assertion(self, checkout, body):
        checkout('test_x.py', _module(body))
        assert len(_run()[1]) >= 1

    @pytest.mark.parametrize('guard', [
        "SKIP = sys.platform == 'win32'",
        "POSIX = sys.platform != 'win32'",
        "WIN = sys.platform.startswith('win')",
        "import os\nPOSIX = os.name != 'nt'",
        "def own(d):\n    return d.replace(b'\\r\\n', b'\\n')",
    ])
    def test_a_guard_or_normalising_replace_passes(self, checkout, guard):
        checkout('test_x.py', _module("def test(): assert b'\\r' not in run('x').stdout\n")
                 + '\n' + guard + '\n')
        assert _run()[1] == []

    @pytest.mark.parametrize('source', [
        # text-mode runs: universal newlines already translate
        "import subprocess\n"
        "def test():\n    r = subprocess.run(['x'], capture_output=True, text=True, timeout=5)\n"
        "    assert r.stdout.count(b'\\n') == 3\n",
        "import subprocess\n"
        "def test():\n    r = subprocess.run(['x'], capture_output=True, encoding='utf-8', timeout=5)\n"
        "    assert r.stdout == b'a\\n'\n",
        # a **kwargs run may carry text mode: unknown, not raw
        "import subprocess\n"
        "def test(kw):\n    r = subprocess.run(['x'], **kw)\n    assert b'\\r' not in r.stdout\n",
        # JSON-parsed assertions
        _module("def test():\n    import json\n"
                "    assert json.loads(run('x').stdout)['n'] == 1\n"),
        # bytes holding no newline literal, or assertions true on Windows too
        _module("def test():\n    r = run('x')\n    assert b'ok' in r.stdout\n"
                "    assert b'\\n' in r.stdout\n    assert r.stdout.endswith(b'\\n')\n"
                "    assert len(r.stdout.splitlines()) == 2\n"),
        # non-subprocess bytes (a fixture file's content), in a module that also runs one
        _module("def test(tmp_path):\n    data = (tmp_path / 'a').read_bytes()\n"
                "    assert b'\\r' not in data\n    assert data == b'a\\n'\n"),
        # building CRLF input is not an assertion on output
        _module("def test(tmp_path):\n    (tmp_path / 'a').write_bytes(b'a\\r\\nb\\r\\n')\n"
                "    assert run('x').returncode == 0\n"),
        # newline literals in a bytes assertion that never touches a subprocess result
        _module("def test():\n    assert b'a\\r\\n'.split(b'\\n') == [b'a\\r', b'']\n"),
        # an unrelated module with no subprocess at all
        "def test(p):\n    assert b'\\r' not in p.read_bytes()\n",
    ])
    def test_negative_controls(self, checkout, source):
        checkout('test_x.py', source)
        assert _run()[1] == []

    def test_noqa_on_the_reported_line(self, checkout):
        checkout('test_x.py', _module(
            "def test():\n"
            "    r = run('x')\n"
            "    assert b'\\r' not in r.stdout  # noqa: V038 reviewed: LF-only stub\n"
            "    assert r.stdout == b'a\\n'\n"))
        assert _lines(_run()[1]) == [('tests/test_x.py', 12)]


class TestScope:
    def test_scans_test_modules_and_conftest_only(self, checkout):
        (Path(checkout('test_a.py', '')).parent / 'fixtures').mkdir()
        bad = PRE_79A576C9
        checkout('helper_fixture.py', bad)
        checkout('fixtures/sample.py', bad)
        checkout('fixtures/test_nested.py', bad)
        checkout('conftest.py', bad)
        _, found = _run()
        assert {d.file_path for d in found} == {
            'tests/fixtures/test_nested.py', 'tests/conftest.py'}

    def test_unparseable_module_is_disclosed_not_skipped(self, checkout):
        checkout('test_broken.py',
                 "import subprocess\nsubprocess.run(['x'])\nassert b'\\r' not in r.stdout(\n")
        rule, found = _run()
        assert found == []
        assert [(o['status'], o['subject']) for o in rule.outcomes] == [
            ('unavailable', 'tests/test_broken.py')]

    def test_installed_package_is_not_applicable(self, tmp_path, monkeypatch):
        root = tmp_path / 'site' / 'reveal'
        for sub in ('analyzers', 'rules'):
            (root / sub).mkdir(parents=True)
        monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
        rule, found = _run()
        assert found == [] and [o['status'] for o in rule.outcomes] == ['skipped']


def test_reveal_own_tests_are_clean(monkeypatch):
    """The rule holds on this checkout's tests/ (what CI's `reveal reveal:// --check` runs)."""
    root = Path(reveal.__file__).parent
    if not (root.parent / 'tests').is_dir():
        pytest.skip('installed package, no tests/')
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    result = check(select=['V038'])
    assert result['detections'] == []
    assert {e['rule']: e['status'] for e in result['coverage']['rules']} == {'V038': 'run'}
