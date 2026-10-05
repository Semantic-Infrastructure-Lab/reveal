"""Behavioral self-check regression and negative controls (BACK-1660)."""
import pytest

from reveal.rules.validation import behavioral_contracts as probes
from reveal.adapters.base import ResourceAdapter
from reveal.adapters.reveal.operations import check
from reveal.adapters.reveal.renderer import RevealRenderer
from reveal.rules import RuleRegistry
from reveal.utils.results import ResultBuilder


@pytest.mark.parametrize('probe', [probes.builder_violations, probes.composition_violations,
                                   probes.pagination_violations, probes.renderer_violations])
def test_live_contracts(probe):
    assert probe() == []


def test_builder_probe_detects_envelope_corruption(monkeypatch):
    original = ResultBuilder.create

    def corrupt(*args, **kwargs):
        data = kwargs.pop('data', None)
        result = original(*args, **kwargs)
        result.update(data or {})
        return result

    monkeypatch.setattr(ResultBuilder, 'create', corrupt)
    assert any('overwrite type' in failure for failure in probes.builder_violations())


def test_builder_probe_detects_dropped_metadata(monkeypatch):
    original = ResultBuilder.create

    def discard(*args, **kwargs):
        kwargs.pop('warnings', None)
        return original(*args, **kwargs)

    monkeypatch.setattr(ResultBuilder, 'create', discard)
    assert any('loses supplied warnings' in failure for failure in probes.builder_violations())


def test_composition_probe_detects_silent_failure(monkeypatch):
    monkeypatch.setattr(ResourceAdapter, 'record_composed_error', lambda *args: None)
    failures = probes.composition_violations()
    assert any('hides returned' in failure for failure in failures)
    assert any('full confidence after raised' in failure for failure in failures)


def test_pagination_probe_detects_invalid_controls(monkeypatch):
    from reveal.utils import query_control
    original = query_control.parse_result_control

    def swallow(query):
        try:
            return original(query)
        except ValueError:
            return '', query_control.ResultControl()

    monkeypatch.setattr(query_control, 'parse_result_control', swallow)
    assert len(probes.pagination_violations()) == 6


def test_renderer_probe_detects_missing_and_duplicate_diagnostics():
    from reveal.adapters.stats.renderer import StatsRenderer

    class BrokenRenderer:
        @staticmethod
        def render_structure(result, format):
            if format == 'json':
                return StatsRenderer.render_structure(result, format)
            print('recorded renderer warning')
            print('recorded renderer warning')

    failures = probes.renderer_violations(BrokenRenderer)
    assert any('duplicates recorded renderer warning' in failure for failure in failures)
    assert any('recorded partial error' in failure for failure in failures)


def test_self_check_routes_all_new_rules():
    result = check(select=['V023', 'V033', 'V034', 'V035'])
    assert result['detections'] == []
    assert result['coverage']['run'] == 4
    assert result['coverage']['failed'] == 0
    assert {entry['rule'] for entry in result['coverage']['rules']} == {'V023', 'V033', 'V034', 'V035'}


def test_rule_crash_is_incomplete_and_cannot_render_all_clear(monkeypatch, capsys):
    from reveal.rules.validation.V033 import V033

    def crash(*args):
        raise RuntimeError('recorded unavailable prerequisite')

    monkeypatch.setattr(V033, 'check', crash)
    result = check(select=['V033'])
    assert result['coverage']['failed'] == 1
    assert result['coverage']['rules'][0]['status'] == 'failed'
    assert 'recorded unavailable prerequisite' in result['errors'][0]['error']
    RevealRenderer.render_check(result)
    output = capsys.readouterr().out
    assert 'incomplete' in output
    assert 'No issues' not in output


def test_non_applicable_rules_have_skip_reason():
    result = check(select=['B001'])
    assert result['coverage']['run'] == 0
    assert result['coverage']['skipped'] == 1
    assert result['coverage']['rules'][0]['reason'] == 'target does not match'
    assert result['error']


def test_legacy_runner_return_type_stays_a_detection_list():
    assert RuleRegistry.check_file('reveal://', None, '', select=['V023']) == []


@pytest.mark.parametrize('key', ['limit', 'offset'])
@pytest.mark.parametrize('raw', ['-1', 'abc', ''])
def test_pagination_rejects_invalid_values(key, raw):
    from reveal.utils.query_control import parse_result_control
    with pytest.raises(ValueError, match=f'{key} must be a non-negative integer'):
        parse_result_control(f'{key}={raw}')


def test_check_failures_exit_nonzero_through_cli(monkeypatch):
    from conftest import _run_reveal_direct
    from reveal.rules.validation.V033 import V033

    def violation(rule, file_path, structure, content):
        return [rule.create_detection(file_path, 1, message='recorded regression')]

    monkeypatch.setattr(V033, 'check', violation)
    result = _run_reveal_direct('reveal://', '--check', '--select', 'V033')
    assert result.returncode == 1
    assert 'recorded regression' in result.stdout


def test_rule_crashes_exit_nonzero_in_json(monkeypatch):
    import json
    from conftest import _run_reveal_direct
    from reveal.rules.validation.V033 import V033

    def crash(*args):
        raise RuntimeError('recorded unavailable prerequisite')

    monkeypatch.setattr(V033, 'check', crash)
    result = _run_reveal_direct('reveal://', '--check', '--select', 'V033', '--format', 'json')
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload['coverage']['failed'] == 1
    assert payload['error']


def test_explicit_metadata_and_scope_are_supported_without_payload_collisions():
    result = ResultBuilder.create('probe', 'probe', meta={'estimated_tokens': 42}, scope={'files': 3})
    assert result['meta'] == {'estimated_tokens': 42}
    assert result['scope'] == {'files': 3}
    with pytest.raises(ValueError, match='meta cannot be combined'):
        ResultBuilder.create('probe', 'probe', meta={}, confidence=1.0)


@pytest.mark.parametrize('code', ['V001', 'V002', 'V003', 'V004', 'V005', 'V006', 'V007',
    'V008', 'V011', 'V012', 'V013', 'V014', 'V015', 'V017', 'V018', 'V019', 'V020',
    'V021', 'V022', 'V024', 'V025', 'V027', 'V028', 'V029', 'V030', 'V031', 'V032'])
def test_missing_root_is_unavailable_not_clean(monkeypatch, code):
    import importlib
    module = importlib.import_module('reveal.rules.validation.' + code)
    monkeypatch.setattr(module, 'find_reveal_root', lambda: None)
    result = check(select=[code])
    assert result['coverage']['unavailable'] == 1
    assert result['coverage']['run'] == 0
    assert result['exit_code'] == 1
    assert result['coverage']['rules'][0]['reason']


def test_missing_docs_and_mixed_completed_checks(monkeypatch, tmp_path, capsys):
    import importlib
    module = importlib.import_module('reveal.rules.validation.V031')
    monkeypatch.setattr(module, 'find_reveal_root', lambda: tmp_path / 'reveal')
    result = check(select=['V031', 'V034'])
    assert result['coverage']['run'] == 1
    assert result['coverage']['unavailable'] == 1
    assert result['exit_code'] == 1
    RevealRenderer.render_check(result)
    text = capsys.readouterr().out
    assert 'V031 unavailable' in text
    assert 'No issues' not in text


@pytest.mark.parametrize('format', ['text', 'json'])
def test_unavailable_root_exits_nonzero_in_cli(monkeypatch, format):
    import importlib
    import json
    from conftest import _run_reveal_direct
    module = importlib.import_module('reveal.rules.validation.V020')
    monkeypatch.setattr(module, 'find_reveal_root', lambda: None)
    result = _run_reveal_direct('reveal://', '--check', '--select', 'V020', '--format', format)
    assert result.returncode == 1
    if format == 'json':
        assert json.loads(result.stdout)['coverage']['unavailable'] == 1
    else:
        assert 'V020 unavailable' in result.stdout
        assert 'No issues' not in result.stdout


def test_missing_registry_import_is_unavailable(monkeypatch):
    import builtins
    original = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name == 'adapters.base':
            raise ImportError('recorded missing registry')
        return original(name, *args, **kwargs)
    RuleRegistry.discover()
    monkeypatch.setattr(builtins, '__import__', unavailable)
    result = check(select=['V020'])
    assert result['coverage']['unavailable'] == 1
    assert 'recorded missing registry' in result['coverage']['rules'][0]['reason']


def test_partial_subject_coverage_counts_rule_once():
    result = check(select=['V020'])
    entry = result['coverage']['rules'][0]
    assert result['coverage']['run'] == 1
    assert entry['subjects']
    assert any(item['status'] == 'run' for item in entry['subjects'])


def test_unavailable_release_endpoint_is_incomplete(monkeypatch):
    from reveal.rules.validation.V032 import V032
    monkeypatch.setattr(V032, '_latest_pypi_version', lambda self: None)
    result = check(select=['V032', 'V034'])
    assert result['coverage']['unavailable'] == 1
    assert result['exit_code'] == 1


def test_unexpected_adapter_initialization_is_not_a_scope_skip():
    from reveal.rules.validation.V020 import V020
    class BrokenAdapter:
        def __init__(self):
            raise RuntimeError('recorded constructor failure')
    rule = V020()
    assert rule._try_instantiate(BrokenAdapter) is None
    assert rule.outcomes[0]['status'] == 'unavailable'
    assert 'recorded constructor failure' in rule.outcomes[0]['reason']
