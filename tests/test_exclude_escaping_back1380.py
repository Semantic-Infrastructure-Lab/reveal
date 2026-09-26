"""BACK-1380: --exclude patterns containing ',' '&' '=' or '%' survived only by luck.

exclude_fragment() comma-joined the patterns and the adapters split on ',' with no
decoding, so `--exclude 'a,b.py'` was split into 'a' and 'b.py' and excluded nothing.
"""
import subprocess
import sys

import pytest

from reveal.cli.routing.flag_specs import exclude_fragment
from reveal.utils.query_parser import join_exclude_patterns, split_exclude_param

TRICKY = ['a,b.py', 'x&y.py', 'k=v.py', '100%.py', '50%2C.py', '*.min.js', 'dir/']


class TestRoundTrip:
    @pytest.mark.parametrize('pattern', TRICKY)
    def test_single_pattern_round_trips(self, pattern):
        assert split_exclude_param(join_exclude_patterns([pattern])) == [pattern]

    def test_list_round_trips_and_keeps_boundaries(self):
        assert split_exclude_param(join_exclude_patterns(TRICKY)) == TRICKY

    def test_plain_patterns_stay_readable(self):
        assert join_exclude_patterns(['vendor', '*.min.js']) == 'vendor,*.min.js'

    def test_hand_written_uri_still_splits_on_comma(self):
        assert split_exclude_param('vendor,build,,') == ['vendor', 'build']

    def test_empty_and_flag_only_values(self):
        assert split_exclude_param(None) == []
        assert split_exclude_param('') == []
        assert split_exclude_param(True) == []

    def test_fragment_is_escaped_and_parses_as_one_query_param(self):
        from reveal.utils.query_parser import parse_query_params
        fragment = exclude_fragment(['a,b.py', 'k=v.py'])
        assert '&' not in fragment and fragment.count('=') == 1
        assert split_exclude_param(parse_query_params(fragment)['exclude']) == ['a,b.py', 'k=v.py']


@pytest.fixture
def tree(tmp_path):
    for name in ('a,b.py', 'c.py', '100%.py'):
        (tmp_path / name).write_text("def f():\n    return 1\n", encoding='utf-8')
    return tmp_path


def run_reveal(*args):
    return subprocess.run([sys.executable, '-m', 'reveal.main'] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          env={**__import__('os').environ, 'REVEAL_DISK_CACHE': '0'})


class TestEndToEnd:
    @pytest.mark.parametrize('pattern', ['a,b.py', '100%.py'])
    def test_stats_exclude(self, tree, pattern):
        proc = run_reveal(f'stats://{tree}', '--exclude', pattern)
        assert proc.returncode == 0, proc.stderr
        assert 'Files:      2' in proc.stdout

    @pytest.mark.parametrize('form', [['overview', '{t}'], ['overview://{t}']])
    def test_overview_exclude(self, tree, form):
        proc = run_reveal(*[a.format(t=tree) for a in form], '--exclude', 'a,b.py')
        assert proc.returncode == 0, proc.stderr
        assert 'Codebase  2 files' in proc.stdout

    def test_pack_exclude(self, tree):
        with_it = run_reveal(f'pack://{tree}')
        without = run_reveal(f'pack://{tree}', '--exclude', 'a,b.py')
        assert 'a,b.py' in with_it.stdout
        assert 'a,b.py' not in without.stdout
