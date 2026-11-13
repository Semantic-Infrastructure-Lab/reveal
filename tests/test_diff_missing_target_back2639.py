"""Missing diff path targets are invalid resources, not analytical findings."""
import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from reveal.adapters.diff.adapter import DiffAdapter


@pytest.mark.parametrize('prefix', ['', 'file://'])
@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_missing_diff_target(tmp_path, side, output_format, prefix):
    present = tmp_path / 'after.py'
    present.write_text('def after():\n    return 1\n', encoding='utf-8')
    missing = tmp_path / 'nope.py'
    left, right = (missing, present) if side == 'left' else (present, missing)
    result = subprocess.run(
        [sys.executable, '-m', 'reveal', f'diff://{prefix}{left}:{prefix}{right}', '--format', output_format],
        capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 2, result.stdout + result.stderr
    assert str(missing) in result.stdout + result.stderr
    if output_format == 'json':
        assert json.loads(result.stdout)['meta']['errors'][0]['code'] == 'invalid_request'


def test_required_read_loss_is_analysis_failure(tmp_path):
    from reveal.cli.routing.uri import resolve_adapter
    from reveal.adapters.diff.renderer import DiffRenderer
    from argparse import Namespace
    left = tmp_path / 'left.py'
    right = tmp_path / 'right.py'
    left.write_text('def left(): pass\n', encoding='utf-8')
    right.write_text('def right(): pass\n', encoding='utf-8')
    args = Namespace(format='json', fail_on=None)
    with patch('reveal.adapters.diff.adapter.resolve_uri', side_effect=PermissionError('read denied')):
        answer = resolve_adapter(DiffAdapter, DiffRenderer, 'diff', f'{left}:{right}', None, args)
    from reveal.utils.results import AnalysisCompleteness, FailureCause
    assert answer.execution_facts.completeness is AnalysisCompleteness.FAILED
    assert answer.execution_facts.failures == frozenset({FailureCause.ANALYSIS})


def test_successful_pair_is_complete(tmp_path):
    from reveal.utils.results import AnalysisCompleteness
    left = tmp_path / 'left.py'
    right = tmp_path / 'right.py'
    for path in (left, right):
        path.write_text('def stable(): pass\n', encoding='utf-8')
    result = DiffAdapter(str(left), str(right)).get_structure()
    assert DiffAdapter.execution_facts(result).completeness is AnalysisCompleteness.COMPLETE
    assert DiffAdapter.uri_execution_facts(f'{left}:{right}') is not None
    assert DiffAdapter.uri_execution_facts('git://HEAD/src:other.py') is None
