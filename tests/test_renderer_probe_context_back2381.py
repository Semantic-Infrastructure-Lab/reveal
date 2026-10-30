"""Recorded renderer probes are independent of their caller's output context."""

from contextlib import redirect_stdout
from io import StringIO
import json
import subprocess

import pytest

from conftest import _run_reveal_direct as run
from reveal.cli.invocation import Invocation, invocation_scope, retirement_note
from reveal.rules.validation.behavioral_contracts import renderer_violations
from reveal.utils import json_utils
from reveal.utils.query_parser import collect_query_keys


@pytest.mark.parametrize('format', ['text', 'json'])
@pytest.mark.parametrize('provenance', [False, True])
def test_selected_renderer_self_check_is_independent_of_output_options(format, provenance):
    response = run('reveal://', '--check', '--select', 'V035', '--format', format,
                   *(['--provenance'] if provenance else []))
    assert response.returncode == 0, (response.stdout, response.stderr)
    if format == 'json':
        answer = json.loads(response.stdout)
        assert answer['detections'] == []
        assert answer['coverage']['run'] == 1
        assert answer['coverage']['failed'] == answer['coverage']['unavailable'] == 0
        assert ('execution' in answer) is provenance
    else:
        assert 'No issues found' in response.stdout


def test_probe_preserves_outer_diagnostics_and_final_writer_still_discloses_them():
    callback_calls = []
    unused = {'type': 'unused_flag', 'code': 'unused_flag', 'fields': ['--depth'],
              'message': 'recorded outer unused input'}
    unknown = {'type': 'unknown_query_param', 'code': 'unknown_query_param',
               'fields': ['bogus'], 'message': 'recorded outer unknown input'}

    def warnings(result):
        callback_calls.append(result)
        return [unused]

    with invocation_scope(Invocation.parse(['reveal://']), retirements_to_stderr=False):
        retirement_note('flag:--calls')
        with collect_query_keys(warnings_to_stderr=False, unused_warnings=warnings) as outer:
            outer.seen.add('bogus')
            outer.warnings.append(unknown)
            violations = renderer_violations()
            assert outer.seen == {'bogus'} and outer.used == set()
            assert outer.warnings == [unknown]
            assert outer.structured_emitted is False
            assert callback_calls == []
            assert violations == []
            output = StringIO()
            with redirect_stdout(output):
                json_utils.print_json_result({'type': 'outer', 'source': 'caller'})
            answer = json.loads(output.getvalue())
            emitted = answer['meta']['warnings']
            assert emitted.count(unknown) == emitted.count(unused) == 1
            assert [warning['field'] for warning in emitted
                    if warning.get('code') == 'retired_spelling'] == ['flag:--calls']
            assert outer.structured_emitted is True
            assert len(callback_calls) == 1


@pytest.mark.parametrize('format', ['text', 'json'])
def test_self_check_still_discloses_actual_unused_outer_input(format):
    response = run('reveal://', '--check', '--select', 'V035', '--depth', '2', '--format', format)
    assert response.returncode == 0, (response.stdout, response.stderr)
    if format == 'json':
        answer = json.loads(response.stdout)
        assert answer['detections'] == []
        assert [warning['fields'] for warning in answer['meta']['warnings']
                if warning['type'] == 'unused_flag'] == [['--depth']]
    else:
        assert '--depth' in response.stderr and 'has no effect' in response.stderr


def test_provenance_enabled_probe_never_launches_a_subprocess(monkeypatch):
    calls = []

    def unexpected(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('renderer probe launched an external process')

    monkeypatch.setattr(subprocess, 'run', unexpected)
    monkeypatch.setattr(json_utils, '_provenance_enabled', True)
    assert renderer_violations() == []
    assert calls == []
    assert json_utils._provenance_enabled is True


@pytest.mark.parametrize('corruption', ['warning', 'error', 'cut', 'source'])
def test_isolated_probe_still_detects_json_corruption(corruption):
    from reveal.adapters.stats.renderer import StatsRenderer

    class BrokenRenderer:
        @staticmethod
        def render_structure(result, format):
            if format == 'json':
                result = {**result, 'meta': dict(result['meta'])}
                if corruption == 'source':
                    result['source'] = 'wrong source'
                elif corruption == 'error':
                    result['meta']['errors'] = []
                else:
                    dropped = 'probe_warning' if corruption == 'warning' else 'truncated'
                    result['meta']['warnings'] = [warning for warning in result['meta']['warnings']
                                                  if warning['type'] != dropped]
            StatsRenderer.render_structure(result, format)

    assert 'Renderer JSON changes recorded diagnostics' in renderer_violations(BrokenRenderer)
