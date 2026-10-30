"""Sprint 3: composed text retains scope, failures and exact cap accounting."""
from argparse import Namespace
from functools import partial
import json
import pytest
from reveal.rendering.adapters.architecture import ArchitectureRenderer, _render_entry_points
from reveal.rendering.adapters.hotspots import HotspotsRenderer
from reveal.rendering.base import emit_rendered
from reveal.cli.routing.subcommand import emit_subcommand_result
from reveal.cli.routing.uri import resolve_uri

pytestmark = pytest.mark.component


def architecture_result():
    return {'path': 'src', 'facts': {'entry_points': [{'file': f'f{i}.py', 'fan_out': i} for i in range(6)]},
            'risks': [], 'next_commands': [], 'meta': {'errors': [{'message': 'partial architecture scan'}]}}


@pytest.mark.parametrize('renderer,result', [
    (ArchitectureRenderer, architecture_result()),
    (HotspotsRenderer, {'path': 'src', 'file_hotspots': [], 'function_hotspots': [],
                        'meta': {'errors': [{'message': 'partial hotspots scan'}]}}),
])
def test_pure_bodies_and_single_diagnostic_owner(renderer, result, capsys):
    body = renderer.render_structure(result)
    assert isinstance(body, str) and not capsys.readouterr().out
    emit_rendered(renderer.render_structure, result)
    output = capsys.readouterr().out
    for error in result['meta']['errors']:
        assert output.count(error['message']) == 1
    assert 'quality looks good' not in output.lower()
    emit_subcommand_result(result, Namespace(format='text'), name='test', source='src',
                           render=partial(renderer.render_structure, format='text'))
    output = capsys.readouterr().out
    for error in result['meta']['errors']:
        assert output.count(error['message']) == 1


@pytest.mark.parametrize('name,renderer', [('architecture', ArchitectureRenderer), ('hotspots', HotspotsRenderer)])
def test_real_failed_result_and_distinct_details(name, renderer, tmp_path, capsys):
    from reveal.cli.routing.uri import _emit_result
    answer = resolve_uri(f'{name}://{tmp_path / "missing"}', Namespace(format='json'))
    assert answer.result.get('error')
    answer.result.update(message='retained detail', next_steps=['check the path'])
    with pytest.raises(SystemExit) as exc:
        _emit_result(answer.result, Namespace(format='text', also_json=None), name, renderer.render_structure)
    output = capsys.readouterr()
    assert exc.value.code == 1 and not output.out
    assert output.err.count('retained detail') == 1
    assert output.err.count('check the path') == 1


def test_architecture_zero_cap_discloses_every_omitted_row():
    from pathlib import Path
    rows = architecture_result()['facts']['entry_points']
    text = '\n'.join(_render_entry_points(rows, 0, Path('src')))
    assert '... and 6 more' in text and 'fan-out' not in text


def test_recorded_framework_warning_is_not_rediscovered(monkeypatch):
    result = architecture_result()
    result['risks'] = [{'type': 'autoload_regime', 'description': 'framework', 'detail': 'recorded framework warning'}]
    def unexpected(*args):
        pytest.fail('renderer rediscovered filesystem state')
    monkeypatch.setattr('reveal.adapters.imports.detect_autoload_regime', unexpected)
    assert 'recorded framework warning' in ArchitectureRenderer.render_structure(result)


def test_stats_exclusions_survive_hotspots_composition(tmp_path, capsys):
    from reveal.adapters.stats import StatsAdapter
    from reveal.adapters.hotspots import HotspotsAdapter
    (tmp_path / 'demo.py').write_text('value = 1\n', encoding='utf-8')
    (tmp_path / 'component.vue').write_text('<template/>', encoding='utf-8')
    for adapter in [StatsAdapter(str(tmp_path)), HotspotsAdapter(str(tmp_path))]:
        result = adapter.get_structure()
        warnings = (result.get('meta') or {}).get('warnings', [])
        matching = [w for w in warnings if w.get('type') == 'unsupported_extensions']
        assert len(matching) == 1 and matching[0]['excluded_by_extension']['.vue'] == 1
        if isinstance(adapter, StatsAdapter):
            assert result['summary']['excluded'] == 1
            (tmp_path / 'component.vue').unlink()
            repeated = adapter.get_structure()
            assert repeated['summary']['excluded'] == 0
            assert not any(w.get('type') == 'unsupported_extensions' for w in repeated.get('meta', {}).get('warnings', []))
            (tmp_path / 'component.vue').write_text('<template/>', encoding='utf-8')
        if isinstance(adapter, HotspotsAdapter):
            emit_rendered(HotspotsRenderer.render_structure, result)
            body = capsys.readouterr().out
            assert body.count('no analyzer is registered') == 1
            assert 'quality looks good' not in body.lower()
