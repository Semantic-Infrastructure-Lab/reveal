"""An invalid regex in an ast:// filter is an invalid request, not an empty answer (BACK-2264).

`query_eval._handle_regex_operator` caught `re.error` and answered "no match", so
`ast://DIR?name~=(` printed `Results: 0 / No matches found` and exited 0, the same as a valid
pattern nothing matches. A broken query must fail loudly naming the pattern and the regex error.
Ordinary AST queries now classify request validation as exit 2 (BACK-2338).
"""

import subprocess
import sys

import pytest

from reveal.adapters.ast.adapter import AstAdapter


@pytest.fixture(scope='module')
def root(tmp_path_factory):
    directory = tmp_path_factory.mktemp('back2264')
    (directory / 'm.py').write_text('@deco\ndef alpha(): pass\n', encoding='utf-8')
    return directory


def _run(root, query):
    return subprocess.run(
        [sys.executable, '-m', 'reveal', f'ast://{root}?{query}'],
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )


def test_valid_pattern_that_matches_nothing_is_still_a_clean_zero(root):
    # Control: only the invalid pattern changes behaviour.
    result = _run(root, 'name~=^zzzz$')
    assert result.returncode == 0
    assert 'Results: 0' in result.stdout


def test_valid_pattern_still_matches(root):
    assert _run(root, 'name~=^alp').returncode == 0
    names = {r['name'] for r in AstAdapter(str(root), 'name~=^alp').get_structure()['results']}
    assert names == {'alpha'}


@pytest.mark.parametrize('query,pattern', [
    ('name~=(', '('), ('decorator~=(', '('), ('name~=[a-', '[a-'), ('name!~(', '('),
])
def test_invalid_pattern_fails_naming_the_pattern(root, query, pattern):
    result = _run(root, query)
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'Results: 0' not in result.stdout
    assert pattern in result.stderr
    assert 'regular expression' in result.stderr.lower() or 'regex' in result.stderr.lower()


def test_pattern_over_the_length_cap_fails(root):
    result = _run(root, 'name~=' + 'a' * 300)
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'too long' in result.stderr.lower()
