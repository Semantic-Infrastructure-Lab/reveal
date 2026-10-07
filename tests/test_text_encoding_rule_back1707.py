"""BACK-1707: V041 (text-mode I/O without encoding=, the Windows cp1252 ratchet of BACK-1354),
the V-series home of scripts/check_text_encoding.py's check.

The parametrized call-classification cases are the script's own unit tests, unchanged. Below:
the ratchet over a fake checkout (STRICT class, baseline at/below/above, both noqa spellings,
a module that does not parse is disclosed) and over this checkout, and the script (kept for
--update-baseline and -v) agreeing with the rule.
"""
import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.adapters.reveal.operations import check
from reveal.rules.validation import V041 as v041
from reveal.rules.validation.V041 import V041

pytestmark = pytest.mark.component

ROOT = Path(__file__).resolve().parent.parent


class cte:
    """The call classifiers, under the name the script's tests used."""
    is_bare_text_io = staticmethod(v041.is_bare_text_io)
    is_strict_site = staticmethod(v041.is_strict_site)


def _call(src):
    return ast.parse(src).body[0].value


@pytest.mark.parametrize('src', [
    "open('a')", "open('a', 'w')", "io.open('a')", "Path('x').read_text()", "Path('x').write_text('d')",
    "p.open()", "p.open('r')", "Path('x').read_text(encoding=None)",
    "tempfile.NamedTemporaryFile('w')", "subprocess.run(['x'], text=True)",
    "subprocess.check_output(['x'], universal_newlines=True)",
])
def test_flags_bare_text_io(src):
    assert cte.is_bare_text_io(_call(src))


@pytest.mark.parametrize('src', [
    "open('a', encoding='utf-8')", "open('a', 'rb')", "open('a', 'wb')", "open(**kw)",
    "Path('x').read_text('utf-8')", "Path('x').read_text(encoding='utf-8')",
    "Path('x').write_text('d', 'utf-8')", "opener.open('http://x')", "dist.read_text('METADATA')",
    "webbrowser.open('http://x')", "tempfile.NamedTemporaryFile('wb')",
    "subprocess.run(['x'], capture_output=True)", "subprocess.run(['x'], text=True, encoding='utf-8')",
    "subprocess.run(['x'], text=False)", "foo.bar()",
])
def test_does_not_flag_safe_or_non_file_calls(src):
    assert not cte.is_bare_text_io(_call(src))


@pytest.mark.parametrize('src, strict', [
    ("(FIXTURES_DIR / 'e.yaml').read_text()", True),
    ("(Path(__file__).parent / 'x').read_text()", True),
    ("open(Path(__file__).parent / 'x')", True),
    ("(tmp_path / 'x').read_text()", False),
    ("open(path)", False),
])
def test_strict_class_is_repo_file_reads(src, strict):
    assert cte.is_strict_site(_call(src)) is strict


BARE = "def f(p):\n    return open(p).read()\n"
BARE_TWICE = "def f(p, q):\n    return open(p).read() + open(q).read()\n"
STRICT = "from pathlib import Path\n\ndef f():\n    return (Path(__file__).parent / 'x').read_text()\n"


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A fake dev checkout the V-rules resolve through REVEAL_DEV_ROOT; returns (writer for
    <tree>/<name> (dedented), writer for the baseline)."""
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
    for sub in ('analyzers', 'rules'):
        (tmp_path / 'reveal' / sub).mkdir(parents=True)
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'scripts').mkdir()
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(tmp_path / 'reveal'))

    def write(rel, source):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return path

    def baseline(counts):
        write(v041.BASELINE_REL, json.dumps(counts))
    return write, baseline


def _run():
    rule = V041()
    return rule, rule.check('reveal://', None, '')


def _lines(detections):
    return sorted((d.file_path, d.line) for d in detections)


def test_attributes():
    rule = V041()
    assert (rule.code, rule.internal, rule.uri_patterns) == ('V041', True, ['^reveal://.*'])


def test_ignores_a_regular_file():
    assert V041().check('reveal/x.py', None, BARE) == []


def test_ratchet_files_above_their_baseline_report_every_site(checkout):
    write, baseline = checkout
    write('reveal/a.py', BARE_TWICE)          # 2 sites, baseline 1: regression
    write('reveal/b.py', BARE)                # 1 site, baseline 1: legacy, quiet
    write('reveal/c.py', BARE)                # 1 site, no baseline entry: regression
    baseline({'reveal/a.py': 1, 'reveal/b.py': 1})
    _, found = _run()
    assert _lines(found) == [('reveal/a.py', 2), ('reveal/a.py', 2), ('reveal/c.py', 2)]
    assert any('1 -> 2' in d.message for d in found) and any('0 -> 1' in d.message for d in found)


def test_ratchet_files_under_their_baseline_are_quiet(checkout):
    write, baseline = checkout
    write('tests/test_a.py', BARE)
    baseline({'tests/test_a.py': 5})
    assert _run()[1] == []


def test_strict_site_in_tests_is_reported_whatever_the_baseline(checkout):
    write, baseline = checkout
    write('tests/test_a.py', STRICT)
    baseline({'tests/test_a.py': 9})
    [d] = _run()[1]
    assert (d.file_path, d.line) == ('tests/test_a.py', 4) and 'STRICT' in d.message


def test_strict_class_only_applies_in_tests(checkout):
    write, baseline = checkout
    write('reveal/a.py', STRICT)
    baseline({'reveal/a.py': 1})
    assert _run()[1] == []


@pytest.mark.parametrize('rel', ['reveal/a.py', 'tests/helper.py', 'scripts/tool.py'])
def test_all_three_trees_are_scanned(checkout, rel):
    write, baseline = checkout
    write(rel, BARE)
    baseline({})
    assert _lines(_run()[1]) == [(rel, 2)]


def test_other_trees_are_not_scanned(checkout):
    write, baseline = checkout
    write('docs/tool.py', BARE)
    baseline({})
    assert _run()[1] == []


@pytest.mark.parametrize('comment', ['# noqa: text-encoding', '# noqa: V041 reviewed'])
def test_both_noqa_spellings_exempt_the_call_line(checkout, comment):
    write, baseline = checkout
    write('reveal/a.py', f"def f(p):\n    return open(p).read()  {comment}\n")
    baseline({})
    assert _run()[1] == []


def test_missing_baseline_means_every_site_is_new(checkout):
    write, _ = checkout
    write('reveal/a.py', BARE)
    assert _lines(_run()[1]) == [('reveal/a.py', 2)]


def test_unparseable_module_is_disclosed_not_skipped(checkout):
    write, baseline = checkout
    write('reveal/broken.py', "def f(:\n")
    write('reveal/ok.py', BARE)
    baseline({})
    rule, found = _run()
    assert [d.file_path for d in found] == ['reveal/ok.py']
    assert any(o['status'] == 'unavailable' for o in rule.outcomes)


def test_detection_posix_path_and_context(checkout):
    write, baseline = checkout
    write('reveal/sub/a.py', BARE)
    baseline({})
    [d] = _run()[1]
    assert d.file_path == 'reveal/sub/a.py' and '\\' not in d.file_path
    assert d.context == 'return open(p).read()'


def test_installed_package_is_not_applicable(tmp_path, monkeypatch):
    root = tmp_path / 'site' / 'reveal'
    for sub in ('analyzers', 'rules'):
        (root / sub).mkdir(parents=True)
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    rule, found = _run()
    assert found == [] and [o['status'] for o in rule.outcomes] == ['skipped']


def test_reveal_own_tree_holds_the_ratchet(monkeypatch):
    """What CI's `reveal reveal:// --check` runs: no STRICT site, no file above its baseline."""
    root = Path(reveal.__file__).parent
    if not (root.parent / 'tests').is_dir():
        pytest.skip('installed package, no tests/')
    monkeypatch.setenv('REVEAL_DEV_ROOT', str(root))
    result = check(select=['V041'])
    assert result['detections'] == []
    assert {e['rule']: e['status'] for e in result['coverage']['rules']} == {'V041': 'run'}


def test_the_maintenance_script_agrees_with_the_rule():
    """scripts/check_text_encoding.py shares V041's scan: clean exactly when the rule is."""
    if not (ROOT / 'scripts' / 'check_text_encoding.py').is_file():
        pytest.skip('installed package, no scripts/')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'check_text_encoding.py')],
                            capture_output=True, text=True, encoding='utf-8', timeout=120,
                            cwd=str(ROOT))
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ratchet OK' in result.stdout
