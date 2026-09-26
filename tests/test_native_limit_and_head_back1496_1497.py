"""BACK-1496 / BACK-1497: result-control flags that used to warn or silently do nothing.

BACK-1496: `--limit N` on hotspots://, calls://, depends:// and testability:// now becomes the
adapter's own `top=N` (declared in CLI_QUERY_FLAGS) instead of "Unknown query param 'limit'";
`--limit 0` means "no cap" everywhere (hotspots' own `top=0` means "nothing"). Adapters with no
natural cap (imports, architecture, deps, ...) keep the warning.

BACK-1497: `--head/--tail/--range` sliced only a single-list result; on a result with several
lists (hotspots://, reveal://) they returned it unchanged in silence.
"""
import json
import os
import subprocess
import sys
from argparse import Namespace

import pytest

import reveal.adapters  # noqa: F401  registers every adapter
from reveal.cli.routing.flag_specs import inject_query_flags
from reveal.cli.routing.uri import _apply_head_tail_range


def run_reveal(*args):
    return subprocess.run([sys.executable, '-m', 'reveal.main', *args], capture_output=True,
                          text=True, encoding='utf-8', env={**os.environ, 'REVEAL_DISK_CACHE': '0'})


def _args(**kw):
    base = dict(since=None, until=None, respect_gitignore=True, all=False, verbose=False,
                sort=None, desc=False, limit=None)
    return Namespace(**{**base, **kw})


NATIVE_CAP = ['hotspots', 'calls', 'depends', 'testability']


class TestLimitBecomesNativeTop:
    @pytest.mark.parametrize('scheme', NATIVE_CAP)
    def test_injects_top_not_limit(self, scheme):
        assert inject_query_flags(f'{scheme}://x', scheme, _args(limit=3)) == f'{scheme}://x?top=3'

    @pytest.mark.parametrize('scheme', NATIVE_CAP)
    def test_zero_means_no_cap(self, scheme):
        assert inject_query_flags(f'{scheme}://x', scheme, _args(limit=0)) == f'{scheme}://x?top=1000000'

    def test_typed_top_is_not_overridden(self):
        assert inject_query_flags('hotspots://x?top=7', 'hotspots', _args(limit=3)) == 'hotspots://x?top=7'

    @pytest.mark.parametrize('scheme', ['imports', 'architecture', 'deps', 'classify'])
    def test_adapters_without_a_cap_keep_the_universal_key(self, scheme):
        assert inject_query_flags(f'{scheme}://x', scheme, _args(limit=3)) == f'{scheme}://x?limit=3'

    def test_zero_is_left_alone_on_universal_adapters(self):
        assert inject_query_flags('ast://x', 'ast', _args(limit=0)) == 'ast://x?limit=0'

    def test_sort_is_still_universal(self):
        assert inject_query_flags('hotspots://x', 'hotspots', _args(sort='name')) == 'hotspots://x?sort=name'


@pytest.fixture
def tree(tmp_path):
    for name in 'abcd':
        body = 'def f(x):\n' + ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12))
        (tmp_path / f'{name}.py').write_text(body + '    return 0\n', encoding='utf-8')
    return tmp_path


def _lists(stdout):
    return {k: len(v) for k, v in json.loads(stdout).items() if isinstance(v, list)}


class TestLimitLive:
    def test_hotspots_limit_caps_both_lists_without_a_warning(self, tree):
        proc = run_reveal(f'hotspots://{tree}', '--limit', '2', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert 'Unknown query param' not in proc.stderr
        lists = _lists(proc.stdout)
        assert lists['file_hotspots'] == 2 and lists['function_hotspots'] == 2

    def test_hotspots_limit_zero_is_uncapped_not_empty(self, tree):
        proc = run_reveal(f'hotspots://{tree}', '--limit', '0', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert _lists(proc.stdout)['file_hotspots'] == 4

    def test_imports_still_warns(self, tree):
        proc = run_reveal(f'imports://{tree}', '--limit', '2', '--format', 'json')
        assert "Unknown query param 'limit'" in proc.stderr


class TestHeadTailRangeOnSeveralLists:
    RESULT = {'file_hotspots': [{'n': i} for i in range(5)],
              'function_hotspots': [{'n': i} for i in range(6)],
              'next_commands': ['a', 'b', 'c'], 'meta': {'warnings': [{'w': 1}] * 3}}

    def _apply(self, capsys, **flags):
        result = json.loads(json.dumps(self.RESULT))
        out = _apply_head_tail_range(result, Namespace(**{'head': None, 'tail': None, 'range': None, **flags}),
                                     scheme='hotspots')
        return out, capsys.readouterr().err

    def test_head_slices_every_list_of_dicts(self, capsys):
        out, err = self._apply(capsys, head=2)
        assert [len(out['file_hotspots']), len(out['function_hotspots'])] == [2, 2]
        assert 'applied to each of file_hotspots, function_hotspots' in err

    def test_tail_and_range(self, capsys):
        out, _ = self._apply(capsys, tail=1)
        assert out['file_hotspots'] == [{'n': 4}] and out['function_hotspots'] == [{'n': 5}]
        out, _ = self._apply(capsys, range=(2, 3))
        assert out['file_hotspots'] == [{'n': 1}, {'n': 2}]

    def test_non_dict_lists_and_nested_meta_untouched(self, capsys):
        out, _ = self._apply(capsys, head=1)
        assert out['next_commands'] == ['a', 'b', 'c'] and len(out['meta']['warnings']) == 3

    def test_no_list_says_so(self, capsys):
        out = _apply_head_tail_range({'name': 'x'}, Namespace(head=2, tail=None, range=None),
                                     scheme='env')
        assert out == {'name': 'x'}
        assert '--head has no effect on env://' in capsys.readouterr().err

    def test_single_list_is_silent_as_before(self, capsys):
        out = _apply_head_tail_range({'results': [{'n': i} for i in range(5)]},
                                     Namespace(head=2, tail=None, range=None), scheme='ast')
        assert len(out['results']) == 2 and capsys.readouterr().err == ''

    def test_no_flag_no_note(self, capsys):
        _apply_head_tail_range({'name': 'x'}, Namespace(head=None, tail=None, range=None))
        assert capsys.readouterr().err == ''

    def test_live_hotspots_head(self, tree):
        proc = run_reveal(f'hotspots://{tree}', '--head', '1', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert _lists(proc.stdout)['file_hotspots'] == 1
