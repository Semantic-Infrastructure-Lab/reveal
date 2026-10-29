"""Health must not manufacture child warnings by forwarding unsupported flags."""

from argparse import Namespace
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.cli.commands.health import _check_uri


@pytest.mark.parametrize('scheme', ['metrics', 'stats'])
@pytest.mark.parametrize('format', ['text', 'json'])
def test_clean_metrics_health_stays_complete(tmp_path, scheme, format):
    (tmp_path / 'clean.py').write_text('value = 1\n', encoding='utf-8')
    response = run('health', f'{scheme}://{tmp_path.as_posix()}', '--format', format)
    assert response.returncode == 0, (response.stdout, response.stderr)
    if format == 'json':
        answer = json.loads(response.stdout)
        assert answer['overall_exit'] == 0
        assert answer['results'][0]['outcome'] == 'ok'
        assert answer['results'][0]['verdict'] == 'healthy'
    else:
        assert 'healthy' in response.stdout
    assert response.stderr.count('note: stats:// is deprecated;') == (scheme == 'stats')


@pytest.mark.parametrize('scheme', ['metrics', 'stats'])
def test_degraded_metrics_health_stays_incomplete(tmp_path, scheme):
    (tmp_path / 'broken.py').write_text('def broken(\n', encoding='utf-8')
    uri = f'{scheme}://{tmp_path.as_posix()}'
    child = run(uri, '--format', 'json')
    # stats:// retains its legacy process policy; health still reads its parse loss.
    assert child.returncode == (3 if scheme == 'metrics' else 0)
    assert any(warning['type'] == 'parse_degraded'
               for warning in json.loads(child.stdout)['meta']['warnings'])
    response = run('health', uri, '--format', 'json')
    assert response.returncode == 3
    answer = json.loads(response.stdout)
    assert answer['overall_exit'] == 3
    assert answer['results'][0]['verdict'] in ('incomplete', 'failed')


@pytest.mark.parametrize('scheme,flags', [
    ('ssl', ['--check', '--advanced', '--only-failures']),
    ('mysql', ['--check', '--advanced', '--only-failures']),
    ('domain', ['--check', '--only-failures']),
])
def test_ops_children_keep_supported_check_controls(scheme, flags):
    child = SimpleNamespace(returncode=0, stdout='{}', stderr='')
    with patch('subprocess.run', return_value=child) as process:
        answer = _check_uri(scheme, f'{scheme}://fixture.invalid', Namespace())
    assert answer.verdict == 'healthy'
    command = process.call_args.args[0]
    assert command[3:] == [f'{scheme}://fixture.invalid', *flags, '--format=json']
    assert process.call_args.kwargs['timeout'] == 120
