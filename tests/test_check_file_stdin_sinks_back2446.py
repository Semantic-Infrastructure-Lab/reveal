"""File and stdin check sinks render each requested view from one analysis."""
import io
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.rules import RuleRegistry

pytestmark = pytest.mark.component
BARE = 'def f():\n    try:\n        return 1\n    except:\n        pass\n'


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'a.py').write_text(BARE + BARE.replace('def f', 'def g'), encoding='utf-8')
    (tmp_path / 'b.py').write_text('def healthy():\n    return 1\n', encoding='utf-8')
    return tmp_path


@pytest.fixture
def scans(monkeypatch):
    calls = []
    real = RuleRegistry.check_file
    def check(*args, **kwargs):
        calls.append(args[0])
        return real(*args, **kwargs)
    monkeypatch.setattr(RuleRegistry, 'check_file', check)
    return calls


def _stdin(project, monkeypatch, fmt, *extra):
    monkeypatch.setattr('sys.stdin', io.StringIO(f'{project / "b.py"}\n{project / "a.py"}\n'))
    return run('--stdin', '--check', '--select', 'B001', '--format', fmt, *extra)


@pytest.mark.parametrize('primary', ['text', 'grep', 'json'])
@pytest.mark.parametrize('sink_format', ['text', 'grep'])
def test_single_file_sink_equals_independent_primary_without_rescanning(project, tmp_path, scans, primary, sink_format):
    source = project / 'a.py'
    separate = run('check', str(source), '--select', 'B001', '--format', sink_format, '--max-items', '1')
    scans.clear()
    destination = tmp_path / 'report.out'
    result = run('check', str(source), '--select', 'B001', '--format', primary, '--max-items', '1',
                 '--output', f'{sink_format}={destination}')
    assert result.returncode == 1, result.stderr
    assert len(scans) == 1
    assert destination.read_text(encoding='utf-8') == separate.stdout
    if sink_format == 'grep':
        assert len(destination.read_text(encoding='utf-8').splitlines()) == 2


@pytest.mark.parametrize('primary', ['text', 'grep', 'json'])
def test_stdin_text_and_grep_sinks_preserve_complete_input_order(project, tmp_path, monkeypatch, scans, primary):
    expected = {fmt: _stdin(project, monkeypatch, fmt).stdout for fmt in ('text', 'grep')}
    scans.clear()
    text, grep, aggregate = (tmp_path / name for name in ('out.txt', 'out.grep', 'out.json'))
    result = _stdin(project, monkeypatch, primary, '--output', f'text={text}',
                    '--output', f'grep={grep}', '--output', f'json={aggregate}')
    assert result.returncode == 1, result.stderr
    assert len(scans) == 2
    assert text.read_text(encoding='utf-8') == expected['text']
    assert grep.read_text(encoding='utf-8') == expected['grep']
    payload = json.loads(aggregate.read_text(encoding='utf-8'))
    assert [Path(row['file']).name for row in payload['files']] == ['b.py', 'a.py']
    assert payload['summary']['total_issues'] == 2


@pytest.mark.parametrize('stdin', [False, True])
def test_failed_text_sink_keeps_other_sink_and_primary_even_with_exit_zero(project, tmp_path, monkeypatch, stdin):
    good, bad = tmp_path / 'ok.grep', tmp_path / 'missing' / 'bad.txt'
    options = ['--exit-zero', '--output', f'text={bad}', '--output', f'grep={good}']
    result = (_stdin(project, monkeypatch, 'json', *options) if stdin else
              run('check', str(project / 'a.py'), '--select', 'B001', '--format', 'json', *options))
    assert result.returncode == 3, result.stderr
    assert good.read_text(encoding='utf-8').count('B001') == 2
    assert result.stderr.count('text output sink failed') == 1
    assert 'Traceback' not in result.stderr
    assert result.stdout.strip()


def test_no_sink_retains_findings_and_uncapped_grep_control(project):
    result = run('check', str(project / 'a.py'), '--select', 'B001', '--format', 'grep', '--max-items', '1')
    assert result.returncode == 1
    assert len(result.stdout.splitlines()) == 2
