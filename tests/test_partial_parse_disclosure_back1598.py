"""BACK-1598: a partial parse is disclosed once, in the result, cold and warm.

The import extractor logged one 'Partial parse for <file>' warning per file per
extraction pass: a cold `reveal overview` of Redis src/ printed 364 such stderr
lines (each file three times, plus one I001 line per file), and a warm run
printed none, because extraction is cached and stdout never said it. Now the
extractor only sets parse_failed, and each command that builds an import graph
states the failed set once: a `partial_parse` meta warning for overview and
architecture (rendered under "Caveats"), a warning line for depends://.
"""

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.component

BROKEN_C = 'int f{i}(int a {{ return a + ; \nvoid g{i}(void) {{ if ( \n'


@pytest.fixture
def tree(tmp_path):
    src = tmp_path / 'proj' / 'src'
    src.mkdir(parents=True)
    (tmp_path / 'proj' / 'Makefile').write_text('all:\n', encoding='utf-8')
    for i in range(3):
        (src / f'broken_{i}.c').write_text('#include "ok.h"\n' + BROKEN_C.format(i=i), encoding='utf-8')
    (src / 'ok.h').write_text('int ok(void);\n', encoding='utf-8')
    (src / 'ok.c').write_text('#include "ok.h"\nint ok(void) { return 1; }\n', encoding='utf-8')
    return src


def _run(args, cache_dir):
    env = dict(os.environ, REVEAL_CACHE_DIR=str(cache_dir), REVEAL_DISK_CACHE='1')
    env.pop('PYTHONPYCACHEPREFIX', None)
    return subprocess.run(
        [sys.executable, '-m', 'reveal', *args],
        capture_output=True, text=True, encoding='utf-8', env=env, timeout=300,
    )


@pytest.mark.parametrize('command', [['overview'], ['architecture']])
def test_disclosed_once_in_the_result_cold_and_warm(tree, tmp_path, command):
    cache = tmp_path / 'cache'
    for run in ('cold', 'warm'):
        text = _run([*command, str(tree)], cache)
        assert 'Partial parse' not in text.stderr, f"{run}: per-file warning reached stderr"
        assert '3 file(s) parsed with errors' in text.stdout, f"{run}: no disclosure in the text"
        assert text.stdout.count('parsed with errors') == 1, f"{run}: disclosed more than once"

        data = _run([*command, str(tree), '--format', 'json'], cache)
        warnings = [w for w in json.loads(data.stdout)['meta']['warnings'] if w['type'] == 'partial_parse']
        assert len(warnings) == 1, f"{run}: {warnings}"
        assert warnings[0]['count'] == 3
        assert warnings[0]['files'] == ['broken_0.c', 'broken_1.c', 'broken_2.c']


def test_depends_discloses_once(tree, tmp_path):
    result = _run([f'depends://{tree}'], tmp_path / 'cache')
    assert 'Partial parse' not in result.stderr
    assert result.stdout.count('3 file(s) parsed with errors') == 1


def test_clean_tree_says_nothing(tmp_path):
    """Positive control for the absence: no partial parse, no warning."""
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'ok.c').write_text('int ok(void) { return 1; }\n', encoding='utf-8')
    data = _run(['overview', str(src), '--format', 'json'], tmp_path / 'cache')
    meta = json.loads(data.stdout).get('meta') or {}
    assert not [w for w in meta.get('warnings') or [] if w['type'] == 'partial_parse']
