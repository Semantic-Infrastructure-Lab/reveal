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
