"""BACK-1707: V039 (POSIX path literals in tests), the V-series home of what
scripts/check_windows_compat.py (BACK-1470) used to scan.

Each sample below is the script's own positive/negative case: the same lines must give the
same findings, a ``# noqa: win-path`` line stays exempt, and the repo's tests are clean.
"""

import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.adapters.reveal.operations import check
from reveal.rules.validation.V039 import V039, find_windows_path_hazards

pytestmark = pytest.mark.component

# Built by concatenation so the repo-wide scan does not read these samples as hazards.
POSIX = '/fa' + 'ke/x.py'
HIT = f"def test_x():\n    assert result['file'] == '{POSIX}'\n"
EXEMPT = f"def test_x():\n    assert result['file'] == '{POSIX}'  # noqa: win-path (plain string)\n"
ASSIGN = f"def test_x(m):\n    m.path = Path('{POSIX}')\n"
SPLIT = "def test_x(r):\n    name = r['file']" + ".rsplit(" + "'/', 1)[-1]\n"


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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return path
    return write


def _run():
    rule = V039()
    return rule, rule.check('reveal://', None, '')


def _lines(detections):
    return sorted((d.file_path, d.line) for d in detections)


def test_attributes():
    rule = V039()
    assert (rule.code, rule.internal, rule.uri_patterns) == ('V039', True, ['^reveal://.*'])


def test_ignores_a_regular_file():
    assert V039().check('tests/test_x.py', None, HIT) == []


@pytest.mark.parametrize('source, pattern', [
    (HIT, 'posix-literal'), (ASSIGN, 'path-assign'), (SPLIT, 'path-split-on-slash')])
def test_scan_names_each_pattern(source, pattern):
    found = find_windows_path_hazards(source.splitlines())
    assert [(line, name) for line, name, _ in found] == [(2, pattern)]


@pytest.mark.parametrize('line', [
    f"assert r == native('{POSIX}')",
    f"assert r == str(Path('{POSIX}'))",
    f"assert r == '{POSIX}'.as_posix()",
    f"assert url == 'https://x/fa' + 'ke/x.py'",
    f"assert r == '{POSIX}'  # noqa: win-path",
    f"# assert r == '{POSIX}'",
    f"x = '{POSIX}'",                                   # not an assertion
    "assert r == '/api/v1/users'",                      # URI-style, not a filesystem root
    f"assertEqual(some_path, Path('{POSIX}'))",         # Path-to-Path
])
def test_scan_negative_controls(line):
    assert find_windows_path_hazards([line]) == []


@pytest.mark.parametrize('rel, source, expected', [
    ('test_a.py', HIT, [('tests/test_a.py', 2)]),
    ('sub/test_b.py', ASSIGN, [('tests/sub/test_b.py', 2)]),
    ('test_c.py', SPLIT, [('tests/test_c.py', 2)]),
    ('test_d.py', EXEMPT, []),
    ('test_nginx_adapter.py', HIT, []),                 # POSIX-data file, exempt as before
    ('helper.py', HIT, []),                             # only test_*.py is scanned
    ('conftest.py', HIT, []),
])
def test_rule_over_a_checkout(checkout, rel, source, expected):
    checkout(rel, source)
    _, found = _run()
    assert _lines(found) == expected


def test_both_noqa_spellings_exempt(checkout):
    checkout('test_a.py', f"def test_x():\n    assert r == '{POSIX}'  # noqa: V039 reviewed\n")
    assert _run()[1] == []


def test_detection_carries_label_advice_and_posix_path(checkout):
    checkout('sub/test_a.py', HIT)
    [d] = _run()[1]
    assert d.file_path == 'tests/sub/test_a.py' and '\\' not in d.file_path
    assert d.message == 'POSIX path literal in assertion'
    assert 'native(' in d.suggestion and d.context.startswith('assert result')


def test_installed_package_is_not_applicable(tmp_path, monkeypatch):
    root = tmp_path / 'site' / 'reveal'
    for sub in ('analyzers', 'rules'):
        (root / sub).mkdir(parents=True)
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    rule, found = _run()
    assert found == [] and [o['status'] for o in rule.outcomes] == ['skipped']


def test_reveal_own_tests_are_clean(monkeypatch):
    """What CI's `reveal reveal:// --check` runs: no unexempted hit anywhere in tests/."""
    root = Path(reveal.__file__).parent
    if not (root.parent / 'tests').is_dir():
        pytest.skip('installed package, no tests/')
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    result = check(select=['V039'])
    assert result['detections'] == []
    assert {e['rule']: e['status'] for e in result['coverage']['rules']} == {'V039': 'run'}
