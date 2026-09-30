"""BACK-1548: file mode cuts --head/--tail/--range once, in the display layer, and says so.

Each analyzer used to slice its own lists (eleven through ``_apply_semantic_slice``, five
by hand), and none could record the cut: ``reveal f.py --head 2 --format json`` returned
2 of 12 functions with no marker, the text said "Functions (2):", and seven analyzers
accepted the flags and dropped them. Now an analyzer returns every item,
``show_structure`` (and ``reveal.api.analyze``) cut the result through
``FileAnalyzer.cut_structure``, and each cut is a ``note_truncation`` entry.
"""

import inspect
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.base import FileAnalyzer
from reveal.registry import get_analyzer_mapping

pytestmark = pytest.mark.component

SIX_FUNCS = ''.join(f'def f{i}():\n    return {i}\n\n\n' for i in range(1, 7))


def _analyzer_classes():
    """Every registered analyzer plus every FileAnalyzer subclass imported so far."""
    classes = set(get_analyzer_mapping().values())
    todo = [FileAnalyzer]
    while todo:
        for sub in todo.pop().__subclasses__():
            if sub not in classes:
                classes.add(sub)
            todo.append(sub)
    return sorted(classes, key=lambda c: f'{c.__module__}.{c.__qualname__}')


def _cuts(result):
    return {w['field']: (w['shown'], w['total'], w['cause'])
            for w in (result.get('meta') or {}).get('warnings') or [] if w.get('type') == 'truncated'}


@pytest.fixture
def six_funcs(tmp_path):
    path = tmp_path / 'six.py'
    path.write_text(SIX_FUNCS, encoding='utf-8')
    return path


@pytest.mark.parametrize('cls', _analyzer_classes(), ids=lambda c: c.__qualname__)
def test_no_analyzer_get_structure_takes_head_tail_or_range(cls):
    """The ratchet: the flags never reach an analyzer, so none may declare them.

    V008 checks the same over reveal/analyzers/ by source; this covers treesitter.py and any
    analyzer a plugin registers.
    """
    params = inspect.signature(cls.get_structure).parameters
    assert not {'head', 'tail', 'range'} & set(params), (
        f'{cls.__qualname__}.get_structure declares {sorted({"head", "tail", "range"} & set(params))}: '
        'return every item and name the lists --head means with SLICE_FIELDS')
    assert cls.SLICE_FIELDS is None or all(isinstance(f, str) for f in cls.SLICE_FIELDS)


def test_the_task_repro_now_discloses_the_cut(six_funcs):
    """'reveal f.py --head 2 --format json' returned 2 of 12 functions and no meta.warnings."""
    run = _run_reveal_direct(six_funcs, '--head', '2', '--format', 'json')
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert [f['name'] for f in out['structure']['functions']] == ['f1', 'f2']
    assert _cuts(out) == {'functions': (2, 6, 'head')}
    assert 'meta' not in out['structure']  # disclosed once, on the envelope


@pytest.mark.parametrize('flag, value, names', [
    ('--tail', '2', ['f5', 'f6']),
    ('--range', '3-4', ['f3', 'f4']),
])
def test_tail_and_range_are_cut_the_same_way(six_funcs, flag, value, names):
    out = json.loads(_run_reveal_direct(six_funcs, flag, value, '--format', 'json').stdout)
    assert [f['name'] for f in out['structure']['functions']] == names
    assert _cuts(out)['functions'][:2] == (2, 6)


def test_text_says_what_the_cut_left_out(six_funcs):
    run = _run_reveal_direct(six_funcs, '--head', '2')
    assert run.stdout.rstrip().endswith('⚠ Truncated functions: showing 2 of 6'), run.stdout


@pytest.mark.parametrize('extra', [['--outline'], ['--typed']])
def test_the_other_text_views_say_so_too(six_funcs, extra):
    run = _run_reveal_direct(six_funcs, '--head', '2', *extra)
    assert '⚠ Truncated functions: showing 2 of 6' in run.stdout, run.stdout


def test_no_cut_no_note(six_funcs):
    run = _run_reveal_direct(six_funcs, '--head', '10')
    assert 'Truncated' not in run.stdout
    out = json.loads(_run_reveal_direct(six_funcs, '--head', '10', '--format', 'json').stdout)
    assert 'warnings' not in out['meta'] and 'meta' not in out['structure']


def test_api_analyze_cuts_like_the_cli(six_funcs):
    result = api.analyze(str(six_funcs), head=2)
    assert [f['name'] for f in result['functions']] == ['f1', 'f2']
    assert _cuts(result) == {'functions': (2, 6, 'head')}


def test_a_flag_the_structure_has_no_list_for_says_so(tmp_path):
    """HTML's overview is dicts: its --head used to print raw lines, now it says it did nothing."""
    page = tmp_path / 'page.html'
    page.write_text('<html><head><title>T</title></head><body><p>x</p></body></html>\n', encoding='utf-8')
    run = _run_reveal_direct(page, '--head', '3')
    assert run.returncode == 0
    assert '--head has no effect on page.html' in run.stderr


def test_csv_head_picks_rows_not_columns(tmp_path):
    table = tmp_path / 't.csv'
    table.write_text('a,b,c\n' + ''.join(f'{i},{i},{i}\n' for i in range(8)), encoding='utf-8')
    out = json.loads(_run_reveal_direct(table, '--head', '2', '--format', 'json').stdout)
    assert out['structure']['columns'] == ['a', 'b', 'c']
    assert len(out['structure']['sample_rows']) == 2
    assert _cuts(out) == {'sample_rows': (2, 8, 'head')}


def test_a_default_sample_is_disclosed(tmp_path):
    """csv's 5-row and jsonl's 10-record samples were cuts with no marker."""
    table = tmp_path / 't.csv'
    table.write_text('a\n' + ''.join(f'{i}\n' for i in range(8)), encoding='utf-8')
    out = json.loads(_run_reveal_direct(table, '--format', 'json').stdout)
    assert _cuts(out) == {'sample_rows': (5, 8, 'sample')}


def test_analyzers_that_dropped_the_flag_now_cut(tmp_path):
    """TOML, JSON, YAML, Dockerfile, nginx and Jupyter accepted --head and ignored it."""
    conf = tmp_path / 'c.toml'
    conf.write_text(''.join(f'[s{i}]\nk = {i}\n' for i in range(4)), encoding='utf-8')
    out = json.loads(_run_reveal_direct(conf, '--tail', '1', '--format', 'json').stdout)
    assert [s['name'] for s in out['structure']['sections']] == ['s3']
    assert _cuts(out)['sections'][:2] == (1, 4)


def test_element_lookup_sees_past_the_display_sample(tmp_path):
    """`reveal f.jsonl @15` said 'No element #15 found': get_structure() held the 10-record sample."""
    log = tmp_path / 'r.jsonl'
    log.write_text(''.join(json.dumps({'type': 't', 'n': i}) + '\n' for i in range(1, 21)),
                   encoding='utf-8')
    run = _run_reveal_direct(log, '@15')
    assert run.returncode == 0, run.stderr
    assert '"n": 15' in run.stdout
