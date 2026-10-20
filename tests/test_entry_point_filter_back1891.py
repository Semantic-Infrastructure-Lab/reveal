"""BACK-1891: the active-entry-point filter has one owner and its numbers state their rule.

``imports://?entrypoints`` lists every file nothing but tests imports ("fan-in 0": 331 on
celery). ``architecture://`` and ``overview://`` report only the *active* ones (78 on celery):
fan_out > 0, not a test file, not ``__init__.py``. Both numbers were printed without saying how
they relate, so they read as contradictory. The fixture below has 4 fan-in-0 files and exactly 1
active entry point:

  app.py            fan-in 0, fan-out 2           active
  orphan.py         fan-in 0, fan-out 0           not active (nothing to run)
  pkg/__init__.py   fan-in 0, fan-out 1           not active (package marker)
  tests/test_app.py fan-in 0, fan-out 1           not active (a test)
  core.py, util.py  imported by app.py            not fan-in 0
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.utils.entry_points import active_entry_points

RULE = 'fan_out > 0, not a test file, not __init__.py'

FILES = {
    'pyproject.toml': '[project]\nname = "probe"\n',
    'app.py': 'import core\nimport util\n',
    'core.py': 'X = 1\n',
    'util.py': 'import core\n',
    'orphan.py': 'Y = 1\n',
    'pkg/__init__.py': 'import core\n',
    'tests/test_app.py': 'import app\n',
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'p'
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _run(*args):
    out = _run_reveal_direct(*args)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _json(*args):
    return json.loads(_run(*args, '--format', 'json'))


EXPECTED = {'fan_in_zero': 4, 'active': 1, 'rule': RULE}


def test_the_fixture_has_four_fan_in_zero_files_and_one_active(project):
    rows = _json(f'imports://{project}?entrypoints')['entries']
    assert sorted(r['file'].rsplit('/', 1)[-1] for r in rows) == [
        '__init__.py', 'app.py', 'orphan.py', 'test_app.py']
    assert [r['file'].rsplit('/', 1)[-1] for r in active_entry_points(rows)] == ['app.py']


def test_architecture_json_counts_fan_in_zero_and_active_and_states_the_rule(project):
    assert _json(f'architecture://{project}')['entry_point_filter'] == EXPECTED


def test_overview_json_counts_fan_in_zero_and_active_and_states_the_rule(project):
    arch = _json(f'overview://{project}?no_git=true')['architecture']
    assert arch['entry_point_filter'] == EXPECTED


def test_architecture_text_states_both_numbers_and_the_rule(project):
    text = _run(f'architecture://{project}')
    assert 'Entry Points  (1 active of 4 fan-in=0 files)' in text
    assert f'active = {RULE}' in text


def test_overview_text_states_both_numbers_and_the_rule(project):
    text = _run(f'overview://{project}?no_git=true')
    assert 'Entry points  (4 fan-in=0, 1 active)' in text
    assert f'active = {RULE}' in text


def test_no_imports_architecture_claims_no_entry_point_counts(project):
    # Negative control: without the import graph there are no entry points to count.
    assert 'entry_point_filter' not in _json(f'architecture://{project}?no_imports=true')


def test_the_filter_counts_by_rule_on_rows():
    rows = [
        {'file': 'a.py', 'fan_out': 3},
        {'file': 'b.py', 'fan_out': 0},
        {'file': 'pkg/__init__.py', 'fan_out': 2},
        {'file': 'tests/x.py', 'fan_out': 5},
        {'file': 'src\\tests\\y.py', 'fan_out': 5},   # Windows spelling of a test path
        {'file': 'src/testing/util.go', 'fan_out': 1},   # not a test directory: stays active
    ]
    from reveal.utils.entry_points import entry_point_filter
    assert [r['file'] for r in active_entry_points(rows)] == ['a.py', 'src/testing/util.go']
    assert entry_point_filter(rows) == {'fan_in_zero': 6, 'active': 2, 'rule': RULE}
