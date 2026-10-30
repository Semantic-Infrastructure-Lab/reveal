"""Sprint 3: composed text retains scope, failures and exact cap accounting."""
from argparse import Namespace
from functools import partial
import json
import pytest
from reveal.rendering.adapters.architecture import ArchitectureRenderer
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.rendering.adapters.hotspots import HotspotsRenderer
from reveal.rendering.base import BaseRenderer, emit_rendered
from reveal.cli.routing.subcommand import emit_subcommand_result
from reveal.cli.routing.uri import resolve_uri

pytestmark = pytest.mark.component


def architecture_result(tmp_path):
    (tmp_path / 'value.py').write_text('VALUE=1\n', encoding='utf-8')
    result = ArchitectureAdapter(str(tmp_path)).get_structure()
    result.setdefault('meta', {}).setdefault('errors', []).append({'message': 'partial architecture scan'})
    return result


@pytest.mark.parametrize('name', ['architecture', 'hotspots'])
def test_pure_bodies_and_single_diagnostic_owner(name, tmp_path, capsys):
    if name == 'architecture':
        renderer, result = ArchitectureRenderer, architecture_result(tmp_path)
    else:
        renderer = HotspotsRenderer
        result = {'path': 'src', 'file_hotspots': [], 'function_hotspots': [],
                  'meta': {'errors': [{'message': 'partial hotspots scan'}]}}
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


@pytest.mark.parametrize('name', ['architecture', 'hotspots'])
def test_real_failed_result_and_distinct_details(name, tmp_path, capsys):
    answer = resolve_uri(f'{name}://{tmp_path / "missing"}', Namespace(format='text'))
    assert answer.result.get('error')
    with pytest.raises(SystemExit) as exc:
        answer.emit()
    output = capsys.readouterr()
    assert exc.value.code == 1 and not output.out
    assert output.err.count(answer.result['error']) == 1

    # Router failures use a preselected generic renderer. Exercise additional
    # failure detail at the shared renderer seam that owns this contract.
    from reveal.cli.routing.uri import _emit_result
    answer.result.update(message='retained detail', next_steps=['check the path'])
    with pytest.raises(SystemExit) as exc:
        _emit_result(answer.result, Namespace(format='text', also_json=None),
                     name, BaseRenderer.render_structure)
    output = capsys.readouterr()
    assert exc.value.code == 1 and not output.out
    assert output.err.count(answer.result['error']) == 1
    assert output.err.count('retained detail') == 1
    assert output.err.count('check the path') == 1


def test_architecture_zero_cap_discloses_every_omitted_row(tmp_path):
    (tmp_path / 'helper.py').write_text('VALUE=1\n', encoding='utf-8')
    for index in range(6):
        (tmp_path / f'entry{index}.py').write_text('from helper import VALUE\n', encoding='utf-8')
    result = ArchitectureAdapter(str(tmp_path), 'top=0').get_structure()
    assert result['map']['entrypoints'] == {'rows': [], 'total': 6, 'returned': 0, 'omitted': 6}
    text = ArchitectureRenderer.render_structure(result)
    assert 'Active entrypoint candidates  (showing 0 of 6 observed)' in text
    assert '  entry0.py  fan-out' not in text


def test_recorded_framework_warning_is_not_rediscovered(tmp_path, monkeypatch):
    result = architecture_result(tmp_path)
    result['map']['metadata']['autoload_regime'] = {'framework': 'Recorded framework', 'evidence': 'recorded marker'}
    def unexpected(*args):
        pytest.fail('renderer rediscovered filesystem state')
    monkeypatch.setattr('reveal.analyzers.imports.views.detect_autoload_regime', unexpected)
    text = ArchitectureRenderer.render_structure(result)
    assert 'Recorded framework' in text and 'recorded marker' in text


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
