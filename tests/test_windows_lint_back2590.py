"""Historical Windows output assertions for the proposed V039 extension.

These exercise the real rule against a fake checkout, using the existing V039
fixture. No replacement scanner is imported by these acceptance tests.
"""
import pytest

from test_windows_path_rule_back1707 import checkout as checkout
from test_windows_path_rule_back1707 import _lines, _run

pytestmark = pytest.mark.component


# Minimal syntax-preserving extracts of the historical constructs. Assignment
# context matters: a legitimate str(error), str(number), or string-source echo
# is not a native Path expectation about a normalized output field.
SINK = """\
def test_sink(tmp_path):
    good, bad = tmp_path / 'good.json', tmp_path / 'no-such-dir' / 'bad.txt'
    result = run('hotspots', '--output', str(bad))
    assert str(bad) in result.stderr
"""
SINK_FIXED = SINK.replace(
    'assert str(bad) in result.stderr',
    "assert 'no-such-dir' in result.stderr and bad.name in result.stderr",
)
SOURCE = """\
def test_source(tmp_path):
    test_file = tmp_path / 'test.py'
    result = ResultBuilder.create(result_type='ast_query', source=test_file)
    assert result['source'] == str(test_file)
"""
SOURCE_FIXED = SOURCE.replace('str(test_file)', 'test_file.as_posix()')
DIRECTORY = """\
def test_directory(tmp_path):
    test_dir = tmp_path / 'src'
    result = ResultBuilder.create(result_type='stats_summary', source=test_dir)
    assert result['source'] == str(test_dir)
"""
DIRECTORY_FIXED = DIRECTORY.replace('str(test_dir)', 'test_dir.as_posix()')
ERROR = """\
def test_error(tmp_path):
    missing = tmp_path / 'missing.py'
    result = ResultBuilder.create_error(result_type='ast_query', source=missing)
    assert result['source'] == str(missing)
"""
ERROR_FIXED = ERROR.replace('str(missing)', 'missing.as_posix()')
UNITTEST = """\
def test_source(self):
    from pathlib import Path as PathlibPath
    from reveal.utils.results import add_cli_contract_fields
    p = PathlibPath('tmp') / 'y'
    enveloped = add_cli_contract_fields({}, result_type='deps', source=p)
    self.assertEqual(enveloped['source'], str(p))
"""
UNITTEST_FIXED = UNITTEST.replace('str(p)', 'p.as_posix()')
REVERSED = SOURCE.replace(
    "result['source'] == str(test_file)", "str(test_file) == result['source']",
)
MULTILINE = SOURCE.replace(
    "assert result['source'] == str(test_file)",
    "assert result['source'] == (\n        str(test_file)\n    )",
)
DIRECT_PATH = """\
from pathlib import Path

def test_source():
    result = ResultBuilder.create(result_type='ast_query', source=Path('tmp') / 'x')
    assert result['source'] == str(Path('tmp') / 'x')
"""

HISTORICAL = [
    pytest.param(SINK, 4, id='22-stderr-path'),
    pytest.param(SOURCE, 4, id='97-file-source'),
    pytest.param(DIRECTORY, 4, id='97-directory-source'),
    pytest.param(ERROR, 4, id='97-error-source'),
    pytest.param(UNITTEST, 6, id='97-unittest-source'),
]
VARIANTS = [
    pytest.param(REVERSED, 4, id='reversed-equality'),
    pytest.param(MULTILINE, 5, id='multiline-str-call'),
    pytest.param(DIRECT_PATH, 5, id='direct-path-constructor'),
]


def _positive_control(write):
    # Split the literal so V039 scanning this test file cannot mistake the
    # fixture data for an assertion in the real suite.
    root = '/fa' + 'ke/control.py'
    write('test_control.py', f"def test_control():\n    assert result['file'] == '{root}'\n")
    return ('tests/test_control.py', 2)


@pytest.mark.parametrize('source,line', HISTORICAL + VARIANTS)
def test_native_path_output_names_file_and_line(checkout, source, line):
    checkout('test_historical.py', source)
    rule, found = _run()
    actual = _lines(found)
    expected = [('tests/test_historical.py', line)]
    assert actual == expected, (
        f'native-path-output: expected V039 finding {expected!r}; got {actual!r}'
    )
    assert rule.outcomes == [], 'fixture scan must not be skipped or unavailable'
    assert [d.rule_code for d in found] == ['V039']


@pytest.mark.parametrize('source', [SINK_FIXED, SOURCE_FIXED, DIRECTORY_FIXED, ERROR_FIXED, UNITTEST_FIXED],
                         ids=['22-fixed', '97-file-fixed', '97-directory-fixed', '97-error-fixed', '97-unittest-fixed'])
def test_actual_historical_fixes_pass_with_a_live_positive_control(checkout, source):
    control = _positive_control(checkout)
    checkout('test_fixed.py', source)
    assert _lines(_run()[1]) == [control], 'actual fix must pass while the control still fires'


@pytest.mark.parametrize('source', [
    "def test_native(tmp_path):\n    assert str(tmp_path) == os.fspath(tmp_path)\n",
    "def test_open(tmp_path):\n    assert open(str(tmp_path / 'x'), encoding='utf-8').read() == 'data'\n",
    "def test_error():\n    error = ValueError('bad')\n    assert result.stderr == str(error)\n",
    "def test_count():\n    number = 42\n    assert result['source'] == str(number)\n",
    "def test_spelling():\n    spelling = 'synthetic'\n    assert result['source'] == str(spelling)\n",
    SOURCE.replace('source=test_file)', 'source=str(test_file))'),
    "def test_mapping(tmp_path):\n    result = {'source': str(tmp_path)}\n    assert result['source'] == str(tmp_path)\n",
    "def test_absent(tmp_path):\n    assert str(tmp_path) not in result.stderr\n",
    "def test_native_version(tmp_path):\n    assert str(tmp_path) in result.stdout\n",
    "def test_metadata(tmp_path):\n    assert metadata['path'] == str(tmp_path)\n",
], ids=['native-comparison', 'filesystem-input', 'exception-string', 'number', 'synthetic-string',
        'explicit-string-source-echo', 'native-mapping-echo', 'negative-leak-guard', 'native-version-output', 'legacy-metadata-path'])
def test_legitimate_native_and_nonpath_strings_are_not_flagged(checkout, source):
    control = _positive_control(checkout)
    checkout('test_legitimate.py', source)
    assert _lines(_run()[1]) == [control], 'negative control must pass without disabling V039'


@pytest.mark.parametrize('suffix', ['# noqa: V039 reviewed', '# noqa: win-path reviewed'])
def test_new_pattern_respects_existing_suppression_spellings(checkout, suffix):
    control = _positive_control(checkout)
    checkout('test_reviewed.py', SOURCE.rstrip() + '  ' + suffix + '\n')
    assert _lines(_run()[1]) == [control]


@pytest.mark.parametrize('name', ['helper.py', 'conftest.py', 'test_nginx_adapter.py'])
def test_new_pattern_keeps_existing_file_exclusions(checkout, name):
    control = _positive_control(checkout)
    checkout(name, SOURCE)
    assert _lines(_run()[1]) == [control]


def test_positive_control_can_detect_a_broken_harness(checkout, monkeypatch):
    control = _positive_control(checkout)
    assert _lines(_run()[1]) == [control]
    monkeypatch.setattr('reveal.rules.validation.V039.load_sources', lambda *args: [])
    with pytest.raises(AssertionError, match='positive-control missing'):
        assert _lines(_run()[1]) == [control], 'positive-control missing'
