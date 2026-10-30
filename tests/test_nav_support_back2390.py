"""Qualified navigation rejections stay distinct from supported empty answers."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from test_conformance_matrix import EXPECTED, LANGUAGES, _sample_path

pytestmark = pytest.mark.component

SQL = Path(__file__).parent / 'fixtures' / 'formats' / 'sql' / 'sample.sql'
STRUCTURAL_FLAGS = ('--outline', '--ifmap', '--catchmap', '--loopmap', '--fanout')


@pytest.fixture
def python_file(tmp_path):
    path = tmp_path / 'example.py'
    path.write_text('def work(a):\n    value = a + 1\n', encoding='utf-8')
    return path


@pytest.mark.parametrize('flag', ('--returns', '--exits', '--ifmap', '--loopmap'))
@pytest.mark.parametrize('fmt', ('text', 'json'))
def test_structure_only_analysis_is_rejected_instead_of_empty_success(flag, fmt):
    result = _run_reveal_direct(SQL, ':1-30', flag, '--format', fmt)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == ''
    assert 'structure-only' in result.stderr
    assert 'sql' in result.stderr.lower()
    assert 'reveal' in result.stderr


@pytest.mark.parametrize('flag', STRUCTURAL_FLAGS)
@pytest.mark.parametrize('depth', ('0', '-1'))
@pytest.mark.parametrize('fmt', ('text', 'json'))
def test_explicit_nonpositive_structural_depth_is_rejected(python_file, flag, depth, fmt):
    result = _run_reveal_direct(python_file, 'work', flag, '--depth', depth, '--format', fmt)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == ''
    assert '--depth' in result.stderr
    assert 'positive' in result.stderr


@pytest.mark.parametrize('language', [*LANGUAGES, 'tsx'])
def test_conformance_navigation_remains_supported(language):
    path = (_sample_path(language) if language != 'tsx' else
            Path(__file__).parent / 'fixtures' / 'smoke' / 'tsx' / 'sample.tsx')
    entry = EXPECTED[language]['entry_function'] if language != 'tsx' else 'processOrder'
    expected = EXPECTED[language]['exits'] if language != 'tsx' else [
        {'kind': 'RETURN', 'line': 16}, {'kind': 'RETURN', 'line': 18}]
    result = _run_reveal_direct(path, entry, '--exits', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert [{'kind': row['kind'], 'line': row['line']}
            for row in json.loads(result.stdout)['findings']] == expected


@pytest.mark.parametrize('flag', ('--returns', '--exits', '--ifmap', '--loopmap'))
def test_supported_empty_analysis_stays_successful(python_file, flag):
    result = _run_reveal_direct(python_file, 'work', flag, '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['findings'] == []


@pytest.mark.parametrize('profile', ('missing', 'untested'))
def test_unknown_measurement_is_not_a_structure_only_denial(python_file, monkeypatch, profile):
    from reveal import capabilities
    if profile == 'missing':
        monkeypatch.delitem(capabilities.CAPABILITIES, 'PythonAnalyzer')
    else:
        original = capabilities.CAPABILITIES['PythonAnalyzer']
        monkeypatch.setitem(capabilities.CAPABILITIES, 'PythonAnalyzer',
                            replace(original, conformance_level=capabilities.CONFORMANCE_UNTESTED))
    result = _run_reveal_direct(python_file, 'work', '--exits', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['findings'] == []


def test_depth_is_not_validated_for_an_analysis_that_does_not_use_it(python_file):
    result = _run_reveal_direct(python_file, 'work', '--exits', '--depth', '0', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['findings'] == []


def test_depth_validation_follows_the_selected_handler(python_file):
    # --exits wins over loopmap in dispatch order.
    result = _run_reveal_direct(python_file, 'work', '--exits', '--loopmap', '--depth', '0',
                                '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['meta']['flag'] == 'exits'


def test_default_structural_depth_is_still_three(python_file):
    result = _run_reveal_direct(python_file, 'work', '--outline', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['meta']['depth'] == 3


@pytest.mark.parametrize('flag', ('--scope', '--around'))
def test_structure_only_line_navigation_is_not_an_analysis_denial(flag):
    result = _run_reveal_direct(SQL, ':3', flag, '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['meta']['flag'] == flag.removeprefix('--')


def test_file_and_markdown_outline_keep_their_depth_policy(tmp_path, python_file):
    result = _run_reveal_direct(python_file, '--outline', '--depth', '0')
    assert result.returncode == 0, result.stderr
    doc = tmp_path / 'guide.md'
    doc.write_text('# Setup\n\n## Details\n\ntext\n', encoding='utf-8')
    result = _run_reveal_direct(doc, 'Setup', '--outline', '--depth', '0')
    assert result.returncode == 0, result.stderr
    assert 'Setup' in result.stdout
    assert '+1 subheadings' in result.stdout


def test_mcp_navigation_reports_unsupported_analysis():
    from reveal.mcp_server import reveal_nav
    result = reveal_nav(str(SQL), ':1-30', 'returns')
    assert 'structure-only' in result
    assert 'No return/exit paths' not in result


def test_registered_mcp_marks_unsupported_analysis_as_error(tmp_path, python_file):
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text

    async def scenario(session):
        rejected = await session.call_tool('reveal_nav', {
            'path': str(SQL.resolve()), 'element': ':1-30', 'flag': 'returns',
        })
        assert rejected.is_error
        assert 'structure-only' in _text(rejected)
        empty = await session.call_tool('reveal_nav', {
            'path': str(python_file), 'element': 'work', 'flag': 'returns',
        })
        assert not empty.is_error
        assert 'No return/exit paths' in _text(empty)

    _run(tmp_path, scenario)


def test_other_explicit_structure_only_profile_rejects_analysis(tmp_path):
    path = tmp_path / 'page.html'
    path.write_text('<html><body><p>Example</p></body></html>\n', encoding='utf-8')
    result = _run_reveal_direct(path, ':1-1', '--exits', '--format', 'json')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == ''
    assert 'structure-only' in result.stderr


def test_structure_only_file_outline_still_answers():
    result = _run_reveal_direct(SQL, '--outline')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
