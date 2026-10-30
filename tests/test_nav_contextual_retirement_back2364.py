"""Contextual navigation corrections leave file and Markdown outlines live."""
from dataclasses import replace
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'work.py'
    path.write_text('def work(a):\n if a:\n  return 1\n return 2\n', encoding='utf-8')
    return path


@pytest.mark.parametrize('old,new,field', [
    ('--outline', '--flow', 'target:nav.outline'),
    ('--outl', '--flow', 'target:nav.outline'),
    ('--ifmap', '--flow=if', 'flag:--ifmap'),
    ('--ifm', '--flow=if', 'flag:--ifmap'),
    ('--loopmap', '--flow=loop', 'flag:--loopmap'),
    ('--catchmap', '--flow=try', 'flag:--catchmap'),
    ('--returns', '--exits', 'flag:--returns'),
    ('--flowto', '--exits', 'flag:--flowto'),
    ('--flowt', '--exits', 'flag:--flowto'),
])
def test_old_navigation_answers_canonically_and_corrects_once(source, old, new, field):
    old_run = _run_reveal_direct(source, 'work', old, '--format', 'json')
    new_run = _run_reveal_direct(source, 'work', new, '--format', 'json')
    old_answer, new_answer = json.loads(old_run.stdout), json.loads(new_run.stdout)
    assert old_run.returncode == new_run.returncode == 0
    assert old_answer['findings'] == new_answer['findings']
    assert old_answer['meta']['flag'] == new_answer['meta']['flag']
    warnings = old_answer['meta']['warnings']
    assert [w['field'] for w in warnings if w['type'] == 'retired_spelling'] == [field]
    assert old_run.stderr.count('deprecated') == 1
    if old == '--flowto':
        assert 'reachability verdict is retired' in old_run.stderr
        assert 'BLOCKED' not in old_run.stdout


def test_outline_context_is_resolved_before_correction(source, tmp_path):
    doc = tmp_path / 'guide.md'
    doc.write_text('# Setup\n\n## Install\n\nUse it.\n', encoding='utf-8')
    for args in [(source, '--outline'), (doc, 'Setup', '--outline')]:
        run = _run_reveal_direct(*args)
        assert run.returncode == 0, run.stderr
        assert 'deprecated' not in run.stderr
    missing = _run_reveal_direct(source, 'absent', '--outline')
    assert missing.returncode == 1
    assert 'deprecated' not in missing.stderr


def test_contextual_outline_error_stage_preserves_other_outline_domains(source, tmp_path, monkeypatch):
    from reveal.cli.invocation import RETIREMENTS
    key = 'target:nav.outline'
    monkeypatch.setitem(RETIREMENTS, key, replace(RETIREMENTS[key], stage='error'))
    rejected = _run_reveal_direct(source, 'work', '--outline')
    assert rejected.returncode == 2
    assert '--flow' in rejected.stderr
    assert rejected.stdout == ''
    assert _run_reveal_direct(source, '--outline').returncode == 0
    doc = tmp_path / 'guide.md'
    doc.write_text('# Setup\n\n## Install\n', encoding='utf-8')
    assert _run_reveal_direct(doc, 'Setup', '--outline').returncode == 0


def test_retirement_teaching_context_distinguishes_code_and_markdown():
    from scripts.check_retired_names import scan
    assert [key for _, key, _ in scan('reveal app.py work --outline')] == ['target:nav.outline']
    assert scan('reveal app.py --outline') == []
    assert scan('reveal guide.md Setup --outline') == []
    assert scan('reveal guide.markdown "Long Heading" --outline') == []
    assert scan('reveal app.py work --flow=if,loop') == []


@pytest.mark.parametrize('command', [
    'reveal --format json app.py work --outline',
    'reveal app.py --format json work --outline',
    'reveal --outline "source folder/app.py" "MyClass.work" --format=json',
])
def test_teaching_uses_actual_global_option_and_positional_identity(command):
    from scripts.check_retired_names import scan
    assert [key for _, key, _ in scan(command)] == ['target:nav.outline']


@pytest.mark.parametrize('command', [
    'reveal --format json app.py --outline',
    'reveal --format json guide.md Setup --outline',
    'reveal guide.markdown --format=json "Long Heading" --outline',
    'reveal --outline "source folder/app.py" --format=json',
])
def test_teaching_global_option_order_preserves_live_outline_domains(command):
    from scripts.check_retired_names import scan
    assert scan(command) == []


def test_ambiguous_flow_prefix_stays_an_argparse_error(source):
    result = _run_reveal_direct(source, 'work', '--flo')
    assert result.returncode == 2
    assert 'ambiguous' in result.stderr


def test_inline_file_line_binding_receives_runtime_contextual_correction(source):
    result = _run_reveal_direct(str(source) + ':2', '--outline', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['meta']['flag'] == 'flow'
    assert [w['field'] for w in answer['meta']['warnings'] if w['type'] == 'retired_spelling'] == [
        'target:nav.outline']


def test_registered_mcp_contextual_error_names_replacement(source, tmp_path):
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text
    code = '''
from dataclasses import replace
from reveal.cli.invocation import RETIREMENTS
from reveal import mcp_server
key = 'target:nav.outline'
RETIREMENTS[key] = replace(RETIREMENTS[key], stage='error')
mcp_server.main()
'''
    doc = tmp_path / 'guide.md'
    doc.write_text('# Setup\n\n## Install\n', encoding='utf-8')

    async def scenario(session):
        rejected = await session.call_tool('reveal_nav', {
            'path': str(source), 'element': 'work', 'flag': 'outline'})
        assert rejected.is_error
        assert '--flow' in _text(rejected)
        assert 'code-element --outline' in _text(rejected)
        live = await session.call_tool('reveal_nav', {
            'path': str(doc), 'element': 'Setup', 'flag': 'outline'})
        assert not live.is_error
        assert 'Install' in _text(live)

    _run(tmp_path, scenario, code)
