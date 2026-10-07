"""BACK-1707: V042 (tests must not feed reveal env:// URIs for variables only POSIX sets), the
V-series home of this file's former tree scan (BACK-1554/1556).

Windows runners have no HOME, USER, SHELL, TERM or LOGNAME. A test that reads env://HOME fails
there only, so the failure first shows up on GitHub's Windows legs after a push; worse, a test
that never checks the URI succeeded passes there while its assertions check nothing. Set a
variable the test owns (monkeypatch.setenv / patch.dict) instead.

The scanner's samples are built from ENV so no literal in this file reads as an input URI.
"""
import ast
import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.adapters.reveal.operations import check
from reveal.rules.validation.V042 import V042, find_posix_env_uris

pytestmark = pytest.mark.component

ENV = 'env:' + '//'


def _scan(source):
    return find_posix_env_uris(ast.parse(source))


def test_scanner_flags_inputs_and_skips_docs_comments_and_rendered_values():
    source = (
        f'"""Module docstring mentioning {ENV}HOME."""\n'
        f'# a comment about {ENV}HOME\n'
        "def test_x():\n"
        f'    """{ENV}USER in a docstring."""\n'
        f"    write('{ENV}PATH\\n{ENV}HOME\\n')\n"
        f"    run('{ENV}SHELL')\n"
        f"    assert '{ENV}HOME:/home/user' in rendered\n"
        f"    run('{ENV}HOMEDRIVE')\n"
    )
    assert _scan(source) == [(5, 'HOME'), (6, 'SHELL')]


@pytest.mark.parametrize('var', ['HOME', 'USER', 'SHELL', 'TERM', 'LOGNAME'])
def test_each_posix_only_variable_is_flagged(var):
    assert _scan(f"x = '{ENV}{var}'\n") == [(1, var)]


@pytest.mark.parametrize('source', [
    f"x = '{ENV}PATH'\n",                                # set on every OS
    f"x = '{ENV}HOMEDRIVE'\n",                           # another variable
    f"x = '{ENV}HOME:/home/user'\n",                     # a rendered value, not an input
    f"def f():\n    '''{ENV}HOME'''\n",                  # docstring
])
def test_scanner_negative_controls(source):
    assert _scan(source) == []


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A fake dev checkout the V-rules resolve through REVEAL_DEV_ROOT; returns a writer
    for <path under the root> (dedented)."""
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
    for sub in ('analyzers', 'rules'):
        (tmp_path / 'reveal' / sub).mkdir(parents=True)
    (tmp_path / 'tests').mkdir()
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(tmp_path / 'reveal'))

    def write(rel, source):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return path
    return write


def _run():
    rule = V042()
    return rule, rule.check('reveal://', None, '')


def _lines(detections):
    return sorted((d.file_path, d.line) for d in detections)


BAD = f"def test_x():\n    run('{ENV}HOME')\n"


def test_attributes():
    rule = V042()
    assert (rule.code, rule.internal, rule.uri_patterns) == ('V042', True, ['^reveal://.*'])


def test_ignores_a_regular_file():
    assert V042().check('tests/test_x.py', None, BAD) == []


@pytest.mark.parametrize('rel, expected', [
    ('tests/test_a.py', [('tests/test_a.py', 2)]),
    ('tests/sub/test_b.py', [('tests/sub/test_b.py', 2)]),
    ('tests/conftest.py', [('tests/conftest.py', 2)]),
    ('tests/helper.py', []),                       # only test_*.py and conftest.py
    ('tests/fixtures/test_sample.py', []),         # fixtures are sample sources
    ('tests/sub/fixtures/test_c.py', [('tests/sub/fixtures/test_c.py', 2)]),   # only the top-level dir
    ('reveal/mod.py', []),                         # production code may name them
])
def test_rule_scans_test_modules_outside_fixtures(checkout, rel, expected):
    checkout(rel, BAD)
    assert _lines(_run()[1]) == expected


def test_noqa_exempts_the_literal_line(checkout):
    checkout('tests/test_a.py', f"def test_x():\n    run('{ENV}HOME')  # noqa: V042 asserts the error\n")
    assert _run()[1] == []


def test_detection_names_the_variable_with_a_posix_path(checkout):
    checkout('tests/sub/test_a.py', BAD)
    [d] = _run()[1]
    assert d.file_path == 'tests/sub/test_a.py' and '\\' not in d.file_path
    assert d.message == f'{ENV}HOME is not set on Windows runners'
    assert d.context == f"run('{ENV}HOME')"


def test_unparseable_module_is_disclosed_not_skipped(checkout):
    checkout('tests/test_broken.py', "def f(:\n")
    checkout('tests/test_ok.py', BAD)
    rule, found = _run()
    assert [d.file_path for d in found] == ['tests/test_ok.py']
    assert any(o['status'] == 'unavailable' for o in rule.outcomes)


def test_installed_package_is_not_applicable(tmp_path, monkeypatch):
    root = tmp_path / 'site' / 'reveal'
    for sub in ('analyzers', 'rules'):
        (root / sub).mkdir(parents=True)
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    rule, found = _run()
    assert found == [] and [o['status'] for o in rule.outcomes] == ['skipped']


def test_no_test_reads_a_posix_only_env_var(monkeypatch):
    """What CI's `reveal reveal:// --check` runs, and what this file's tree scan used to assert."""
    root = Path(reveal.__file__).parent
    if not (root.parent / 'tests').is_dir():
        pytest.skip('installed package, no tests/')
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    result = check(select=['V042'])
    assert result['detections'] == []
    assert {e['rule']: e['status'] for e in result['coverage']['rules']} == {'V042': 'run'}
