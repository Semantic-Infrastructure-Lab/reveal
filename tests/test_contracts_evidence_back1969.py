"""Contract facts retain their own failed and recovered input population."""
from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.adapters.ast import analysis, nav_surface_common
from reveal.adapters.contracts import ContractsAdapter, _with_analysis_skipped

pytestmark = pytest.mark.component

SAMPLES = {
    'py': ('from abc import ABC\nclass Contract(ABC):\n    pass\n', 'broken = (\n'),
    'ts': ('export interface Contract { go(): void; }\n', 'const broken = ;\n'),
    'go': ('package p\ntype Contract interface { Go() }\n', 'func broken( {\n'),
    'rs': ('trait Contract { fn go(&self); }\n', 'fn broken( {\n'),
    'rb': ('module Contract\n def go; end\nend\n', 'class Broken <\n'),
    'cpp': ('class Contract { public: virtual void go() = 0; };\n', 'void broken( {\n'),
}


@pytest.mark.parametrize('extension', SAMPLES)
@pytest.mark.parametrize('recovered', [False, True])
def test_real_scanners_retain_contracts_and_recovery(tmp_path, extension, recovered):
    clean, malformed = SAMPLES[extension]
    file = tmp_path/('contracts.'+extension)
    file.write_text(clean + (malformed if recovered else ''), encoding='utf-8')
    result = ContractsAdapter(str(tmp_path)).get_structure()
    assert result['total_contracts'] == 1
    assert result['coverage']['analyzed_files'] == 1
    assert bool(result.get('recovered_files')) is recovered
    warnings = [w for w in result['meta']['warnings'] if w.get('type') == 'parse_recovered']
    assert bool(warnings) is recovered
    if recovered:
        assert result['recovered_files'] == [file.as_posix()]
        assert warnings[0]['count'] == 1
    assert not result.get('error') and not result['meta']['errors']


def test_all_failed_shared_structures_are_loaded_once_and_count_distinct_inputs(tmp_path):
    for name in ('a.py', 'b.ts'):
        (tmp_path/name).write_text('irrelevant\n', encoding='utf-8')
    with patch.object(analysis, 'create_element_dict', side_effect=OSError('exact producer read failure')) as producer:
        result = ContractsAdapter(str(tmp_path)).get_structure()
    assert producer.call_count == 2
    warning, = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert warning['count'] == 2
    assert result['coverage']['analyzed_files'] == 0
    assert len(result['meta']['errors']) == 2
    assert all('OSError: exact producer read failure' in e['message'] for e in result['meta']['errors'])
    assert 'analysis_skipped' not in result


def test_native_success_is_not_missing_due_to_unrelated_shared_analysis(tmp_path):
    (tmp_path/'a.py').write_text(SAMPLES['py'][0], encoding='utf-8')
    (tmp_path/'b.go').write_text(SAMPLES['go'][0], encoding='utf-8')
    original = analysis.create_element_dict

    def fail_go(file, *args, **kwargs):
        if file.endswith('.go'):
            raise OSError('unrelated shared Go structure failure')
        return original(file, *args, **kwargs)

    with patch.object(analysis, 'create_element_dict', side_effect=fail_go):
        result = ContractsAdapter(str(tmp_path)).get_structure()
    assert result['by_language']['go']['protocols'][0]['name'] == 'Contract'
    assert result['coverage']['analyzed_files'] == 2
    assert not result['meta']['errors']
    assert not any(w.get('type') == 'analysis_failed' for w in result['meta']['warnings'])


@pytest.mark.parametrize('extension', ['go', 'rs', 'rb', 'cpp'])
def test_native_failure_retains_exact_cause_and_reduces_coverage_once(tmp_path, extension):
    file = tmp_path/('contracts.'+extension)
    file.write_text(SAMPLES[extension][0], encoding='utf-8')
    with patch.object(nav_surface_common, 'get_tree', side_effect=OSError('exact native parse failure')):
        result = ContractsAdapter(str(tmp_path)).get_structure()
    assert result['unparsed_files'] == [file.as_posix()]
    assert result['coverage']['analyzed_files'] == 0
    error, = result['meta']['errors']
    assert error['file'] == file.as_posix()
    assert 'OSError: exact native parse failure' in error['message']
    assert result['total_contracts'] == 0


def test_duplicate_failure_channels_count_each_input_once(tmp_path):
    file = (tmp_path/'a.py').as_posix()
    report = {'coverage': {'analyzed_files': 2}, 'unparsed_files': [file, file]}
    result = _with_analysis_skipped(report, [(file, 'OSError: first'), (file, 'OSError: first'),
                                             (file, 'ValueError: second')])
    assert result['coverage']['analyzed_files'] == 1
    assert len(result['analysis_skipped']) == 1
    assert result['unparsed_files'] == [file]
    assert all(cause in result['analysis_skipped'][0][1] for cause in ('first', 'second'))


def test_empty_and_unsupported_inventories_remain_nonfatal(tmp_path):
    empty = ContractsAdapter(str(tmp_path)).get_structure()
    (tmp_path/'source.lua').write_text('local value = 1\n', encoding='utf-8')
    unsupported = ContractsAdapter(str(tmp_path)).get_structure()
    for result in (empty, unsupported):
        assert result['total_contracts'] == 0 and not result.get('error')
        assert not result['meta']['errors']
        assert 'recovered_files' not in result
    assert unsupported['coverage']['warning']
