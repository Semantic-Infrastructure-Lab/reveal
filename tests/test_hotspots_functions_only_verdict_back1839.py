"""overview:// must not surface the typo warning for its own internal complexity filter (BACK-1839 F12).

hotspots suppressed the warning privately; overview runs the same kind of internal AST
query (``complexity>9``) and printed "Filter key(s) 'complexity' never appear ... this may
be a typo" on a tree with no function to carry the key. The suppression now lives in one
shared helper both adapters call.
"""

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.cli


def _run(*args):
    return subprocess.run([sys.executable, '-m', 'reveal', *map(str, args)],
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


@pytest.fixture(scope='module')
def no_function_tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('nofn')
    (root / 'consts.py').write_text('A = 1\nB = 2\n', encoding='utf-8')
    return root


@pytest.mark.parametrize('form', ['cli', 'uri'])
def test_overview_text_has_no_internal_filter_typo_warning(no_function_tree, form):
    args = (('overview', no_function_tree, '--no-git') if form == 'cli'
            else (f'overview://{no_function_tree}?no_git=true',))
    result = _run(*args)
    assert result.returncode == 0, result.stderr
    assert 'Filter key(s)' not in result.stdout + result.stderr
    assert 'typo' not in result.stdout + result.stderr


def test_overview_json_has_no_unknown_filter_key_entry(no_function_tree):
    result = _run('overview', no_function_tree, '--no-git', '--format', 'json')
    assert result.returncode == 0, result.stderr
    warnings = (json.loads(result.stdout).get('meta') or {}).get('warnings') or []
    assert [w for w in warnings if w.get('type') == 'unknown_filter_key'] == []


# Negative controls: a typo in a USER query still warns; hotspots stays quiet.
def test_user_written_unknown_filter_key_still_warns(no_function_tree):
    result = _run(f'ast://{no_function_tree}?complexity_typo>3')
    assert "Filter key(s) 'complexity_typo' never appear" in result.stdout + result.stderr


def test_hotspots_still_quiet_on_empty_function_population(no_function_tree):
    result = _run('hotspots', no_function_tree)
    assert result.returncode == 0
    assert 'Filter key(s)' not in result.stdout + result.stderr


# F4: the clean verdict under --functions-only is keyed on the coverage of the scan that ran.
CLEAN_VERDICT = 'No hotspots found ✅  Code quality looks good.'


@pytest.fixture(scope='module')
def clean_tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('clean')
    (root / 'm.py').write_text('def small():\n    return 1\n', encoding='utf-8')
    return root


@pytest.fixture(scope='module')
def syntax_tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('syntax')
    (root / 'm.py').write_text('def small():\n    return 1\n', encoding='utf-8')
    (root / 'bad.py').write_text('def broken(:\n    pass\n', encoding='utf-8')
    return root


@pytest.mark.parametrize('form', ['cli', 'uri'])
def test_clean_functions_only_scan_prints_the_clean_verdict(clean_tree, form):
    args = (('hotspots', clean_tree, '--functions-only') if form == 'cli'
            else (f'hotspots://{clean_tree}?functions_only=true',))
    result = _run(*args)
    assert result.returncode == 0, result.stderr
    assert CLEAN_VERDICT in result.stdout


def test_default_mode_clean_verdict_is_unchanged(clean_tree):
    assert CLEAN_VERDICT in _run('hotspots', clean_tree).stdout


@pytest.mark.parametrize('form', ['cli', 'uri'])
def test_functions_only_discloses_a_parse_failure_and_is_not_clean(syntax_tree, form):
    args = (('hotspots', syntax_tree, '--functions-only') if form == 'cli'
            else (f'hotspots://{syntax_tree}?functions_only=true',))
    result = _run(*args)
    assert result.returncode == 0, result.stderr
    assert '1 file(s) did not parse cleanly' in result.stdout
    assert CLEAN_VERDICT not in result.stdout


def test_default_mode_parse_failure_disclosure_is_unchanged(syntax_tree):
    result = _run('hotspots', syntax_tree)
    assert '1 file(s) did not parse cleanly' in result.stdout
    assert CLEAN_VERDICT not in result.stdout


def test_empty_tree_functions_only_is_not_clean(tmp_path):
    result = _run('hotspots', tmp_path, '--functions-only')
    assert CLEAN_VERDICT not in result.stdout


def test_functions_only_still_lists_a_real_hotspot(tmp_path):
    body = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(15))
    (tmp_path / 'hot.py').write_text(f'def hot(x):\n{body}    return 0\n', encoding='utf-8')
    result = _run('hotspots', tmp_path, '--functions-only')
    assert 'hot' in result.stdout and CLEAN_VERDICT not in result.stdout
