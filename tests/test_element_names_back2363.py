"""Mechanical nav names preserve complete answers, modes and source spans."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from test_conformance_matrix import EXPECTED, EXTENSIONS

pytestmark = pytest.mark.conformance
NAMES = {'deps': 'inputs', 'mutations': 'outputs', 'writes': 'outputs', 'calls': 'callsites'}


def cases():
    for language in [*sorted(EXPECTED), 'tsx']:
        if language == 'tsx':
            path = Path('tests/fixtures/smoke/tsx/sample.tsx')
            element, selected = 'processOrder', '13-13'
        else:
            path = Path('tests/fixtures/conformance') / language / ('sample.' + EXTENSIONS[language])
            element = EXPECTED[language]['entry_function']
            selected = EXPECTED[language]['mutations_probe']['range']
        for old in ('deps', 'mutations', 'calls'):
            for mode, positionals, extra in [
                ('named', [element], []), ('range', [':' + selected], []), ('flat', [], []),
                ('selected', [element], [selected] if old == 'calls' else ['--range', selected]),
            ]:
                yield pytest.param(path, old, positionals, extra, id=f'{language}-{old}-{mode}')


def without_note(answer, old):
    warnings = answer['meta'].get('warnings', [])
    assert len(warnings) == 1 and warnings[0]['field'] == 'flag:--' + old
    assert warnings[0]['code'] == 'retired_spelling'
    del answer['meta']['warnings']
    return answer


@pytest.mark.parametrize('path,old,positionals,extra', list(cases()))
def test_new_and_retired_names_have_identical_complete_answers(path, old, positionals, extra):
    canonical = run(path.as_posix(), *positionals, '--' + NAMES[old], *extra, '--format', 'json')
    assert canonical.returncode == 0, canonical.stderr
    answer = json.loads(canonical.stdout)
    assert answer['meta']['flag'] == NAMES[old]
    assert not answer['meta'].get('warnings') and 'deprecated' not in canonical.stderr
    legacy = run(path.as_posix(), *positionals, '--' + old, *extra, '--format', 'json')
    assert legacy.returncode == canonical.returncode
    assert without_note(json.loads(legacy.stdout), old) == answer
    assert legacy.stderr.count(f'--{old} is deprecated; use --{NAMES[old]}.') == 1


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'sample.py'
    path.write_text('def extract(value):\n    total = len(value)\n'
                    '    answer = transform(total, outside)\n    return answer\n', encoding='utf-8')
    return path.as_posix()


def test_inputs_keep_candidate_and_builtin_distinction(source):
    response = run(source, 'extract', '--inputs', '--format', 'json')
    assert response.returncode == 0
    findings = json.loads(response.stdout)['findings']
    assert {'kind': 'builtin', 'var': 'len', 'line': 2, 'first_write_line': None} in findings
    assert {'kind': 'dep', 'var': 'outside', 'line': 3, 'first_write_line': None} in findings


def test_outputs_are_range_hazards_and_callsites_keep_optional_range(source):
    whole = run(source, 'extract', '--outputs', '--format', 'json')
    assert whole.returncode == 0 and json.loads(whole.stdout)['findings'] == []
    ranged = run(source, ':2-2', '--outputs', '--format', 'json')
    assert ranged.returncode == 0
    assert json.loads(ranged.stdout)['findings'] == [
        {'kind': 'mutation', 'var': 'total', 'line': 2, 'next_read_line': 3}]
    for old in ('mutations', 'writes'):
        legacy = run(source, ':2-2', '--' + old, '--format', 'json')
        assert without_note(json.loads(legacy.stdout), old) == json.loads(ranged.stdout)
    calls = run(source, 'extract', '--callsites', '3-3', '--format', 'json')
    assert calls.returncode == 0
    result = json.loads(calls.stdout)
    assert (result['meta']['from_line'], result['meta']['to_line']) == (3, 3)
    assert len(result['findings']) == 1 and result['findings'][0]['line'] == 3


def test_provenance_records_actual_spelling_and_json_retirement_is_parseable(source):
    import shlex

    current_args = [source, 'extract', '--inputs', '--provenance', '--format', 'json']
    old_args = [source, 'extract', '--deps', '--provenance', '--format', 'json']
    current = run(*current_args)
    old = run(*old_args)
    assert current.returncode == old.returncode == 0
    canonical, legacy = json.loads(current.stdout), json.loads(old.stdout)
    assert canonical['execution']['command'] == shlex.join(['reveal', *current_args])
    assert legacy['execution']['command'] == shlex.join(['reveal', *old_args])
    legacy = without_note(legacy, 'deps')
    legacy['execution']['command'] = canonical['execution']['command']
    assert legacy == canonical


def test_callsites_equals_range_and_retired_equals_spelling(source):
    current = run(source, 'extract', '--callsites=3-3', '--format', 'json')
    old = run(source, 'extract', '--calls=3-3', '--format', 'json')
    assert current.returncode == old.returncode == 0
    answer = json.loads(current.stdout)
    assert (answer['meta']['from_line'], answer['meta']['to_line']) == (3, 3)
    assert without_note(json.loads(old.stdout), 'calls') == answer
    assert old.stderr.count('--calls is deprecated; use --callsites.') == 1


@pytest.mark.parametrize('abbreviation,old', [('mutation', 'mutations'), ('writ', 'writes')])
def test_abbreviated_retired_flags_cannot_bypass_notes_or_cut(source, abbreviation, old, monkeypatch):
    from reveal.cli.invocation import RETIREMENTS, Retirement

    key = 'flag:--' + old
    entry = RETIREMENTS[key]
    response = run(source, 'extract', '--' + abbreviation, '--format', 'json')
    assert response.returncode == 0 and response.stderr.count(entry.text) == 1
    without_note(json.loads(response.stdout), old)
    monkeypatch.setitem(RETIREMENTS, key, Retirement(entry.old, entry.replacement, 'error'))
    rejected = run(source, 'extract', '--' + abbreviation)
    assert rejected.returncode == 2 and rejected.stdout == ''
    assert entry.text in rejected.stderr
    assert run(source, 'extract', '--outputs').returncode == 0


@pytest.mark.parametrize('old', list(NAMES))
def test_alias_text_notes_once_repeats_per_invocation_and_cut_stage_is_two(source, old, monkeypatch):
    from reveal.cli.invocation import RETIREMENTS, Retirement

    for _ in range(2):
        current = run(source, 'extract', '--' + NAMES[old])
        legacy = run(source, 'extract', '--' + old, '--' + old)
        assert legacy.returncode == current.returncode == 0
        assert legacy.stdout == current.stdout
        assert legacy.stderr.count('is deprecated; use') == 1
    key = 'flag:--' + old
    entry = RETIREMENTS[key]
    monkeypatch.setitem(RETIREMENTS, key, Retirement(entry.old, entry.replacement, 'error'))
    rejected = run(source, 'extract', '--' + old, '--format', 'json')
    assert rejected.returncode == 2 and rejected.stdout == ''
    assert entry.text in rejected.stderr
    assert run(source, 'extract', '--' + NAMES[old]).returncode == 0


@pytest.mark.parametrize('path', [
    'reveal/docs/guides/NAV_GUIDE.md', 'tests/fixtures/formats/sql/sample.sql',
    'tests/fixtures/formats/hcl/sample.tf', 'tests/fixtures/formats/powershell/sample.ps1',
])
@pytest.mark.parametrize('old', ['deps', 'mutations', 'calls'])
def test_non_function_resources_preserve_existing_outcome(path, old):
    canonical = run(path, ':1-5', '--' + NAMES[old], '--format', 'json')
    legacy = run(path, ':1-5', '--' + old, '--format', 'json')
    assert canonical.returncode == legacy.returncode
    if canonical.returncode:
        assert canonical.stdout == legacy.stdout
        assert canonical.stderr in legacy.stderr
    else:
        assert without_note(json.loads(legacy.stdout), old) == json.loads(canonical.stdout)


def test_actual_sdk_nav_names_alias_notes_and_request_isolation(source, tmp_path):
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text

    async def scenario(session):
        for old, new in NAMES.items():
            canonical = await session.call_tool('reveal_nav', {'path': source, 'element': 'extract', 'flag': new})
            assert not canonical.is_error and 'deprecated' not in _text(canonical)
            for _ in range(2):
                legacy = await session.call_tool('reveal_nav', {'path': source, 'element': 'extract', 'flag': old})
                assert not legacy.is_error
                assert _text(legacy).startswith(_text(canonical).rstrip('\n'))
                assert _text(legacy).count(f'--{old} is deprecated; use --{new}.') == 1
        ranged = await session.call_tool('reveal_nav', {
            'path': source, 'element': 'extract', 'flag': 'callsites', 'flag_value': '3-3'})
        assert not ranged.is_error and 'transform' in _text(ranged) and 'len(' not in _text(ranged)
        assert not (await session.call_tool('reveal_nav', {
            'path': source, 'element': ':2-2', 'flag': 'outputs'})).is_error
        literal = await session.call_tool('reveal_nav', {
            'path': source, 'element': 'extract', 'flag': 'varflow', 'flag_value': '--writes'})
        assert not literal.is_error and 'deprecated' not in _text(literal)

    _run(tmp_path, scenario)


def test_actual_sdk_cut_stage_is_an_authored_error(source, tmp_path):
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text
    code = '''
from reveal import mcp_server
from reveal.cli.invocation import RETIREMENTS, Retirement
row = RETIREMENTS['flag:--deps']
RETIREMENTS['flag:--deps'] = Retirement(row.old, row.replacement, 'error')
mcp_server.main()
'''

    async def scenario(session):
        old = await session.call_tool('reveal_nav', {'path': source, 'element': 'extract', 'flag': 'deps'})
        assert old.is_error and '--deps is deprecated; use --inputs.' in _text(old)
        current = await session.call_tool('reveal_nav', {'path': source, 'element': 'extract', 'flag': 'inputs'})
        assert not current.is_error and 'deprecated' not in _text(current)

    _run(tmp_path, scenario, code)
