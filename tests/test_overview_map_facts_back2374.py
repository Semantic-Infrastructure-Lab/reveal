"""Qualification of the bounded, unwired map projection (BACK-2374)."""
from copy import deepcopy
from pathlib import Path

import pytest

from reveal.analyzers.imports import resolution, service
from reveal.analyzers.imports.map_facts import project_map_facts
from reveal.analyzers.imports.views import ImportView
from reveal.utils.entry_points import active_entry_points


def answers(root):
    built = service.analyze(service.path_scope(root))
    view = ImportView(built.analysis, root, resolution.ScanRoot(root, 'path'), service.DEFAULT_FILE_CAP)
    with service.composed_rules('overview://'):
        return view.fan_in(), view.entrypoints(), view.components(), view.circular(), view.get_metadata()


@pytest.fixture
def source():
    rule = {'text': 'fixture static import rule', 'lazy': 'include', 'tests': 'include', 'scope': 'scanned_path'}
    fans = [{'file': f'pkg/a{n}.py', 'fan_in': 9-n, 'fan_out': 1} for n in range(8)]
    entries = [{'file': f'pkg/e{n}.py', 'fan_out': 1, 'is_test': False,
                'test_only_importers': 2} for n in range(8)]
    entries += [{'file': 'tests/test_a.py', 'fan_out': 1}, {'file': 'pkg/__init__.py', 'fan_out': 1},
                {'file': 'pkg/leaf.py', 'fan_out': 0}]
    components = [{'component': f'pkg/c{n}', 'files': 2, 'internal': 1, 'outgoing': 3,
                   'incoming': 4, 'cohesion': None, 'cohesion_reason': 'declined fixture',
                   'top_bridge': f'pkg/c{n}/a.py'} for n in range(8)]
    groups = [[f'pkg/c{n}/a{i}.py' for i in range(8)] for n in range(8)]
    metadata = {'scanned_files': 32, 'files_failed_count': 1, 'files_failed': ['pkg/broken.py'],
                'files_lost_count': 0, 'files_lost': [],
                'extraction_diagnostics': {'pkg/broken.py': {'parse': {'reason': 'exact cause'}}},
                'unsupported_extensions': {'.lua': 2}, 'autoload_regime': {'framework': 'fixture'},
                'scan_budget': {'total': 100, 'returned': 32, 'exact': True, 'capped': True}}
    return ({'entries': fans, 'total': len(fans), 'edge_rule': rule},
            {'entries': entries, 'total_scanned': 32, 'edge_rule': rule},
            {'components': components, 'total': len(components), 'edge_rule': rule,
             'cohesion_rule': 'fixture cohesion rule'},
            {'cycles': groups, 'cycle_paths': [g+[g[0]] for g in groups], 'count': len(groups),
             'edge_rule': {**rule, 'lazy': 'exclude', 'text': 'fixture load-time rule'}}, metadata)


@pytest.mark.parametrize('top', [0, 1, 5, 20])
def test_exact_bounds_and_selected_fields(source, tmp_path, top):
    before = deepcopy(source)
    result = project_map_facts(*source, path=tmp_path, top=top)
    for section in ('fan_in', 'entrypoints', 'components', 'cycles'):
        assert result[section]['total'] == 8
        assert result[section]['returned'] == min(top, 8)
        assert result[section]['omitted'] == max(8-top, 0)
        assert len(result[section]['rows']) == min(top, 8)
    assert result['entry_point_filter']['fan_in_zero'] == 11
    assert result['entry_point_filter']['active'] == 8
    assert result['metadata'] == source[4]
    assert result['rules']['cohesion_rule'] == 'fixture cohesion rule'
    if top:
        assert result['components']['rows'][0] == source[2]['components'][0]
        assert result['entrypoints']['rows'][0]['test_only_importers'] == 2
        cycle = result['cycles']['rows'][0]
        assert cycle['members']['total'] == 8
        assert cycle['members']['returned'] == min(top, 8)
        assert cycle['path']['total'] == 9
        assert cycle['path']['returned'] == min(top, 9)
    assert source == before
    result['metadata']['scan_budget']['total'] = 999
    assert source == before


def test_windows_spelling_normalized_at_every_path_sink(source, tmp_path):
    source[0]['entries'][0]['file'] = 'pkg\\a.py'
    source[1]['entries'][0]['file'] = 'pkg\\__init__.py'
    source[2]['components'][0].update(component='pkg\\sub', top_bridge='pkg\\sub\\a.py', files=10)
    source[3]['cycles'][0][0] = 'pkg\\a.py'
    source[3]['cycle_paths'][0][0] = 'pkg\\a.py'
    source[4]['files_failed'] = ['pkg\\broken.py']
    source[4]['extraction_diagnostics'] = {'pkg\\broken.py': {'parse': {'reason': 'exact cause'}}}
    result = project_map_facts(*source, path=tmp_path)
    assert result['fan_in']['rows'][0]['file'] == 'pkg/a.py'
    assert result['entry_point_filter']['active'] == 7
    assert result['components']['rows'][0]['component'] == 'pkg/sub'
    assert result['components']['rows'][0]['top_bridge'] == 'pkg/sub/a.py'
    assert result['cycles']['rows'][0]['members']['rows'][0] == 'pkg/a.py'
    assert result['cycles']['rows'][0]['path']['rows'][0] == 'pkg/a.py'
    assert result['metadata']['files_failed'] == ['pkg/broken.py']
    assert result['metadata']['extraction_diagnostics'] == {'pkg/broken.py': {'parse': {'reason': 'exact cause'}}}


@pytest.mark.parametrize('section,field', [(0, 'total'), (2, 'total'), (3, 'count')])
def test_pre_cut_producer_cannot_become_exact(source, tmp_path, section, field):
    source[section][field] += 1
    with pytest.raises(ValueError, match='complete'):
        project_map_facts(*source, path=tmp_path)


@pytest.mark.parametrize('top', [-1, True, 1.5])
def test_invalid_bound_is_rejected(source, tmp_path, top):
    with pytest.raises(ValueError, match='top'):
        project_map_facts(*source, path=tmp_path, top=top)


def test_no_graph_is_not_successful_empty(tmp_path):
    with pytest.raises((KeyError, ValueError)):
        project_map_facts({}, {}, {}, {}, {}, path=tmp_path)


def test_major_components_rank_size_before_cohesion(source, tmp_path):
    source[2]['components'][0].update(files=1, cohesion=1.0)
    source[2]['components'][1].update(files=10, cohesion=0.0)
    result = project_map_facts(*source, path=tmp_path, top=2)
    assert [r['component'] for r in result['components']['rows']] == ['pkg/c1', 'pkg/c2']
    assert result['rules']['component_order'] == 'covered file count descending, then component path ascending'


def test_losses_keep_every_cause_and_existing_path_cap_at_top_zero(source, tmp_path):
    metadata = source[4]
    metadata.update(files_failed_count=53, files_lost_count=53,
                    files_failed=[f'failed{n:02}.py' for n in range(50)],
                    files_lost=[f'failed{n:02}.py' for n in range(50)],
                    extraction_diagnostics={f'failed{n:02}.py': {'parse': {'reason': f'cause {n}'}}
                                            for n in range(53)})
    result = project_map_facts(*source, path=tmp_path, top=0)
    assert result['metadata'] == metadata
    assert len(result['metadata']['extraction_diagnostics']) == 53
    assert result['metadata']['files_lost_count'] == 53
    assert result['metadata']['scan_budget']['capped'] is True


def test_zero_fan_in_rows_are_not_ranked_as_relationships(source, tmp_path):
    source[0]['entries'][-1]['fan_in'] = 0
    result = project_map_facts(*source, path=tmp_path, top=20)
    assert result['fan_in']['total'] == 7
    assert result['fan_in']['returned'] == 7
    assert result['fan_in']['omitted'] == 0


@pytest.mark.parametrize('damage', ['loss', 'causes', 'count', 'witness', 'rule'])
def test_malformed_source_cannot_become_clean_map(source, tmp_path, damage):
    if damage == 'loss':
        source[4]['files_failed'] = []
    elif damage == 'causes':
        source[4]['extraction_diagnostics'] = None
    elif damage == 'count':
        source[0]['entries'][0]['fan_in'] = -1
    elif damage == 'witness':
        source[3]['cycle_paths'].pop()
    else:
        source[0].pop('edge_rule')
    with pytest.raises(ValueError):
        project_map_facts(*source, path=tmp_path)


def test_actual_empty_graph_is_exact(tmp_path):
    result = project_map_facts(*answers(tmp_path), path=tmp_path)
    for section in ('fan_in', 'entrypoints', 'components', 'cycles'):
        assert result[section] == {'rows': [], 'total': 0, 'returned': 0, 'omitted': 0}
    assert result['metadata']['scanned_files'] == 0


LANGUAGES = ['python', 'javascript', 'typescript', 'rust', 'go', 'java', 'c', 'cpp',
             'csharp', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'dart', 'lua', 'zig', 'gdscript', 'tsx']


@pytest.mark.parametrize('language', LANGUAGES)
def test_real_conformance_views_preserve_their_answers(language):
    fixtures = Path(__file__).parent / 'fixtures'
    root = (fixtures / ('smoke' if language == 'tsx' else 'conformance') / language).resolve()
    raw = answers(root)
    result = project_map_facts(*raw, path=root, top=10000)
    assert result['fan_in']['total'] == sum(e['fan_in'] > 0 for e in raw[0]['entries'])
    assert result['entrypoints']['total'] == len(active_entry_points(raw[1]['entries']))
    assert result['components']['total'] == raw[2]['total']
    assert result['cycles']['total'] == raw[3]['count']
    assert result['metadata']['scan_budget'] == raw[4]['scan_budget']
    assert result['metadata']['unsupported_extensions'] == raw[4]['unsupported_extensions']


def test_real_test_local_and_typechecking_counting_rules(tmp_path):
    for name, text in {
        'a.py': 'from b import value\ndef f():\n    from c import value\n',
        'b.py': 'from a import f\nvalue = 1\n',
        'c.py': 'from a import f\nvalue = 1\n',
        'entry.py': 'from a import f\n',
        'tests/test_entry.py': 'from entry import f\n',
        'typed.py': 'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from entry import f\n',
    }.items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding='utf-8')
    result = project_map_facts(*answers(tmp_path), path=tmp_path, top=20)
    fans = {r['file']: r for r in result['fan_in']['rows']}
    assert fans['c.py']['fan_in'] == 1  # function-local counts in fan-in
    assert fans['entry.py']['fan_in'] == 1  # tests count, TYPE_CHECKING does not
    assert 'entry.py' in {r['file'] for r in result['entrypoints']['rows']}
    assert result['cycles']['total'] == 1
    assert set(result['cycles']['rows'][0]['members']['rows']) == {'a.py', 'b.py'}
    assert 'edge_rule_sections' in result['rules']
