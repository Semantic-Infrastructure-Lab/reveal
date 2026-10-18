"""Known required Calls loss survives six owners and presentation boundaries."""

import json
import os
from pathlib import Path

import pytest

from reveal.adapters.ast import analysis
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls.adapter import CallsRenderer
from reveal.adapters.calls import index


MODES = [
    ('target=leaf&depth=2', 'total_callers'),
    ('callees=entry', 'total_calls'),
    ('root=entry', 'total_resolved'),
    ('uncalled&top=1', 'total_defined'),
    ('rank=callers&top=1', 'total_unique_callees'),
    ('modules', 'total_edges'),
]


def make_tree(root, *, survivors=True):
    root.mkdir()
    child = root / 'included_child'
    child.mkdir()
    source = ('from leaf import leaf\n\ndef entry():\n    return leaf()\n')
    (child / 'hidden.py').write_text(source, encoding='utf-8')
    if survivors:
        (root / 'entry.py').write_text(source, encoding='utf-8')
        (root / 'leaf.py').write_text('def leaf():\n    return 1\n', encoding='utf-8')
    return child


def deny_child(monkeypatch, child):
    real = os.scandir

    def scandir(directory):
        if Path(directory) == child:
            raise PermissionError(13, 'controlled included child loss', str(child))
        return real(directory)

    monkeypatch.setattr(os, 'scandir', scandir)


def required(result):
    return [w for w in result['meta']['warnings']
            if w.get('type') in ('analysis_failed', 'analysis_incomplete')]


def assert_loss(result):
    (warning,) = required(result)
    assert warning['type'] == 'analysis_incomplete'
    assert warning['directories'] == ['included_child']
    assert warning['count'] == 1
    assert warning['unit'] == 'directories'
    assert any('PermissionError:' in cause and 'controlled included child loss' in cause
               for cause in warning['causes'])
    assert 'missing file population is unknown' in warning['message']
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_partial'
    assert 'analysis_skipped' not in result
    assert 'analysis_traversal_failures' not in result
    return warning


@pytest.mark.parametrize('query,count', MODES)
@pytest.mark.parametrize('survivors', [False, True])
def test_real_directory_loss_all_modes(tmp_path, monkeypatch, query, count, survivors):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    child = make_tree(root, survivors=survivors)
    make_tree(sibling)
    clean = CallsAdapter(str(sibling), query).get_structure()
    with monkeypatch.context() as context:
        deny_child(context, child)
        result = CallsAdapter(str(root), query).get_structure()
        assert result[count] > 0 if survivors else result[count] == 0
        assert CallsAdapter(str(sibling), query).get_structure() == clean
        assert_loss(result)
    assert not required(CallsAdapter(str(root), query).get_structure())


@pytest.mark.parametrize('query,count', MODES)
@pytest.mark.parametrize('survivors', [False, True])
def test_real_loss_text_once(tmp_path, monkeypatch, capsys, query, count, survivors):
    root = tmp_path / 'affected'
    child = make_tree(root, survivors=survivors)
    deny_child(monkeypatch, child)
    result = CallsAdapter(str(root), query).get_structure()
    CallsRenderer.render_structure(result)
    output = capsys.readouterr()
    assert (output.out + output.err).count('missing file population is unknown') == 1


@pytest.mark.parametrize('query', ['target=leaf', 'root=entry', 'modules'])
@pytest.mark.parametrize('query_override', [False, True])
def test_real_loss_dot_and_json_channels(tmp_path, monkeypatch, capsys, query, query_override):
    root = tmp_path / 'affected'
    child = make_tree(root)
    deny_child(monkeypatch, child)
    suffix = '&format=dot' if query_override else ''
    result = CallsAdapter(str(root), query + suffix).get_structure()
    CallsRenderer.render_structure(result, 'json' if query_override else 'dot')
    output = capsys.readouterr()
    assert output.out.startswith('digraph ')
    assert output.out.rstrip().endswith('}')
    assert 'missing file population' not in output.out
    assert output.err.count('missing file population is unknown') == 1
    result.pop('_query_format', None)
    CallsRenderer.render_structure(result, 'json')
    output = capsys.readouterr()
    assert_loss(json.loads(output.out))
    assert not output.err


def test_required_file_loss_withholds_confidence_and_uncalled_wording(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    make_tree(root)
    real = analysis.create_element_dict

    def fail(path, *args, **kwargs):
        if Path(path).name == 'leaf.py':
            raise ValueError('controlled file loss')
        return real(path, *args, **kwargs)

    monkeypatch.setattr(analysis, 'create_element_dict', fail)
    result = CallsAdapter(str(root), 'uncalled').get_structure()
    assert required(result)
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_partial'
    warning = next(w for w in result['meta']['warnings'] if w.get('code') == 'W-CALLS-5')
    assert 'confidence above' not in warning['message']
    assert 'withheld' in warning['message']
    assert 'Zero callers found is not proof of dead code.' in warning['message']


def test_supplied_known_loss_propagates_warm_index(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    child = make_tree(root)
    warm = index.build_callers_index(str(root))
    deny_child(monkeypatch, child)
    supplied = analysis.collect_structures(str(root))
    partial = index.build_callers_index(str(root), supplied)
    assert partial is not warm
    assert getattr(partial, 'traversal_failures', ()) == supplied.traversal_failures


@pytest.mark.parametrize('query,count', MODES)
def test_clean_empty_is_full_and_warning_only_controls_keep_score(tmp_path, query, count):
    result = CallsAdapter(str(tmp_path), query).get_structure()
    assert result[count] == 0
    assert not required(result)
    assert result['meta']['parse_mode'] == 'tree_sitter_full'
    assert result['meta']['confidence'] == 0.85
