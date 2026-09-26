"""BACK-1496 / BACK-1497: result-control flags that used to warn or silently do nothing.

BACK-1496: `--limit N` on hotspots://, calls://, depends:// and testability:// now becomes the
adapter's own `top=N` (declared in CLI_QUERY_FLAGS) instead of "Unknown query param 'limit'";
`--limit 0` means "no cap" everywhere (hotspots' own `top=0` means "nothing"). Adapters with no
natural cap (imports, architecture, deps, ...) keep the warning. Modes that ignore top= say so
(calls://?target=) or honor it (depends://<file>), rather than dropping --limit in silence.

BACK-1497: `--head/--tail/--range` sliced only a single-list result; on a result with several
lists (hotspots://, reveal://) they returned it unchanged in silence. Adapters now declare every
sliceable list in BUDGET_LIST_FIELD (a tuple); undeclared lists are never guessed at, and the
renderers count what they show.
"""
import json
import os
import subprocess
import sys
from argparse import Namespace

import pytest

import reveal.adapters  # noqa: F401  registers every adapter
from reveal.adapters.base import get_adapter_class
from reveal.cli.routing.flag_specs import inject_query_flags
from reveal.cli.routing.uri import _apply_head_tail_range, _find_budget_list_field


def run_reveal(*args):
    return subprocess.run([sys.executable, '-m', 'reveal.main', *args], capture_output=True,
                          text=True, encoding='utf-8', env={**os.environ, 'REVEAL_DISK_CACHE': '0'})


def _args(**kw):
    base = dict(since=None, until=None, respect_gitignore=True, all=False, verbose=False,
                sort=None, desc=False, limit=None)
    return Namespace(**{**base, **kw})


def _nav(**kw):
    return Namespace(**{'head': None, 'tail': None, 'range': None, **kw})


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

    def test_all_and_limit_collide_with_a_note(self, capsys):
        uri = inject_query_flags('hotspots://x', 'hotspots', _args(all=True, limit=2))
        assert uri == 'hotspots://x?top=1000000'
        assert 'Note: --limit ignored on hotspots:// -- --all already sets top=' in capsys.readouterr().err

    def test_universal_limit_collision_is_noted_too(self, capsys):
        # ast:// --all is limit=1000000, so --all --limit always dropped --limit in silence.
        assert inject_query_flags('ast://x', 'ast', _args(all=True, limit=2)) == 'ast://x?limit=1000000'
        assert 'Note: --limit ignored on ast:// -- --all already sets limit=' in capsys.readouterr().err

    def test_distinct_keys_do_not_collide(self, capsys):
        uri = inject_query_flags('git://x', 'git', _args(since='2026-01-01', limit=2))
        assert uri == 'git://x?since=2026-01-01&limit=2'
        assert capsys.readouterr().err == ''


@pytest.fixture
def tree(tmp_path):
    for name in 'abcd':
        body = 'def f(x):\n' + ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12))
        (tmp_path / f'{name}.py').write_text(body + '    return 0\n', encoding='utf-8')
    return tmp_path


@pytest.fixture
def imported(tmp_path):
    (tmp_path / 'lib.py').write_text('def helper():\n    return 1\n', encoding='utf-8')
    for name in 'abcde':
        (tmp_path / f'{name}.py').write_text(
            'from lib import helper\n\ndef run():\n    return helper()\n', encoding='utf-8')
    return tmp_path


def _json(stdout):
    return json.loads(stdout)


def _lists(stdout):
    return {k: len(v) for k, v in _json(stdout).items() if isinstance(v, list)}


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

    def test_calls_target_mode_says_top_is_ignored(self, imported):
        proc = run_reveal(f'calls://{imported}?target=helper', '--limit', '1', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert "Query param 'top' (--limit) for calls:// only caps ?rank=callers" in proc.stderr

    def test_calls_target_mode_all_is_quiet(self, imported):
        proc = run_reveal(f'calls://{imported}?target=helper', '--all', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert "Query param 'top'" not in proc.stderr

    def test_depends_file_mode_honors_limit_and_keeps_the_total(self, imported):
        proc = run_reveal(f'depends://{imported}/lib.py', '--limit', '2', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        data = _json(proc.stdout)
        assert len(data['dependents']) == 2 and data['count'] == 5
        text = run_reveal(f'depends://{imported}/lib.py', '--limit', '2').stdout
        assert '5 file(s) import this module (showing 2)' in text

    def test_depends_summary_says_top_n_of_total(self, imported):
        (imported / 'm.py').write_text('import a\n', encoding='utf-8')
        text = run_reveal(f'depends://{imported}', '--limit', '1').stdout
        assert 'Top 1 of 2 module(s) imported internally' in text

    @pytest.mark.parametrize('flag', ['--limit', '--head', '--tail'])
    def test_negative_counts_are_rejected(self, tree, flag):
        proc = run_reveal(f'hotspots://{tree}', flag, '-1')
        assert proc.returncode == 1
        assert f'Error: {flag} must be 0 or more, got -1' in proc.stderr


class TestHeadTailRangeOnSeveralLists:
    RESULT = {'file_hotspots': [{'n': i} for i in range(5)],
              'function_hotspots': [{'n': i} for i in range(6)],
              'risks': [{'r': i} for i in range(4)],
              'next_commands': ['a', 'b', 'c']}

    def _apply(self, capsys, adapter=None, **flags):
        result = json.loads(json.dumps(self.RESULT))
        adapter = adapter or get_adapter_class('hotspots')
        out = _apply_head_tail_range(result, _nav(**flags), adapter, scheme='hotspots')
        return out, capsys.readouterr().err

    def test_head_slices_each_declared_list(self, capsys):
        out, err = self._apply(capsys, head=2)
        assert [len(out['file_hotspots']), len(out['function_hotspots'])] == [2, 2]
        assert 'applied to each of file_hotspots, function_hotspots' in err

    def test_undeclared_lists_are_never_guessed_at(self, capsys):
        out, _ = self._apply(capsys, head=1)
        assert len(out['risks']) == 4 and out['next_commands'] == ['a', 'b', 'c']

    def test_tail_and_range(self, capsys):
        out, _ = self._apply(capsys, tail=1)
        assert out['file_hotspots'] == [{'n': 4}] and out['function_hotspots'] == [{'n': 5}]
        out, _ = self._apply(capsys, range=(2, 3))
        assert out['file_hotspots'] == [{'n': 1}, {'n': 2}]

    def test_declared_field_absent_is_left_alone_silently(self, capsys):
        # calls:// declares 'levels'/'entries'; claude:// applies --head itself in post_process.
        # A declared adapter whose result lacks its fields is not second-guessed.
        result = {'other': [{'n': i} for i in range(5)]}
        out = _apply_head_tail_range(result, _nav(head=2), get_adapter_class('claude'), scheme='claude')
        assert len(out['other']) == 5 and capsys.readouterr().err == ''

    def test_undeclared_adapter_with_no_list_says_so(self, capsys):
        out = _apply_head_tail_range({'name': 'x'}, _nav(head=2), get_adapter_class('env'),
                                     scheme='env')
        assert out == {'name': 'x'}
        assert '--head has no effect on env://' in capsys.readouterr().err

    def test_single_list_is_silent_as_before(self, capsys):
        out = _apply_head_tail_range({'results': [{'n': i} for i in range(5)]}, _nav(head=2),
                                     get_adapter_class('ast'), scheme='ast')
        assert len(out['results']) == 2 and capsys.readouterr().err == ''

    def test_no_flag_no_note(self, capsys):
        _apply_head_tail_range({'name': 'x'}, _nav())
        assert capsys.readouterr().err == ''

    def test_budget_field_stays_single(self):
        # --max-items still applies to one list only (multi-list budgeting: BACK-1498).
        hotspots = get_adapter_class('hotspots')
        assert _find_budget_list_field(dict(self.RESULT), hotspots) is None
        assert _find_budget_list_field({'file_hotspots': []}, hotspots) == 'file_hotspots'

    def test_live_hotspots_head(self, tree):
        proc = run_reveal(f'hotspots://{tree}', '--head', '1', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert _lists(proc.stdout)['file_hotspots'] == 1

    def test_live_calls_ranking_header_counts_what_it_shows(self, imported):
        text = run_reveal(f'calls://{imported}?rank=callers', '--head', '1').stdout
        assert 'Showing:               1 of ' in text
