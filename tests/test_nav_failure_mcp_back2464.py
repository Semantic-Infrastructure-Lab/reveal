"""Authored nav source failures survive the actual SDK and stdio boundary."""
import asyncio
import json
import logging
from pathlib import Path

import pytest

pytest.importorskip('mcp')
from mcp.types import CallToolRequestParams

from conftest import _run_reveal_direct
from reveal.utils.results import FailureCause, NavSourceFailure, failure_execution_facts
from test_mcp_expected_errors_back1992 import _run as _stdio, _text
from test_nav_traversal_loss_back2025 import fault

pytestmark = [pytest.mark.mcp, pytest.mark.component]
FLAGS = ['effects', 'sideeffects', 'boundary', 'inputs']


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.py'
    path.write_text('import logging\ndef empty():\n    return 1\ndef work(value):\n'
                    '    logging.info(value)\n    return value\ndef ambiguous():\n    helper()\n', encoding='utf-8')
    for name in ('a.py', 'b.py'):
        (tmp_path / name).write_text('def helper():\n    open("hidden", "w")\n', encoding='utf-8')
    return path


def _arguments(path, element='empty', flag='effects', **controls):
    return dict(path=str(path), element=element, flag=flag, **controls)


def _sdk(arguments):
    from reveal.mcp_server import mcp

    async def call():
        return await mcp._handle_call_tool(None, CallToolRequestParams(name='reveal_nav', arguments=arguments))
    return asyncio.run(call())


def _diagnostic(text, missing):
    # A missing path is refused before the command line runs, as reveal_element refuses it (BACK-2627 X13).
    phrase = 'path not found' if missing else 'could not find function or method'
    assert text.count(phrase) == 1, text
    assert 'Traceback' not in text and 'Internal error' not in text
    if not missing:
        assert text.count('list available elements') == 1 and text.count('Class.method') == 1


@pytest.mark.parametrize('flag', FLAGS)
@pytest.mark.parametrize('missing', [True, False])
def test_direct_and_registered_missing_source_or_element_are_authored(source, flag, missing):
    from reveal.mcp_server import reveal_nav, _ToolFailure

    arguments = _arguments(source.parent / 'missing.py' if missing else source,
                           'empty' if missing else 'absent', flag)
    direct = reveal_nav(**arguments)
    answer = _sdk(arguments)
    assert answer.is_error, _text(answer)
    assert isinstance(direct, _ToolFailure) and direct.public
    _diagnostic(direct, missing)
    _diagnostic(_text(answer), missing)


@pytest.mark.parametrize('code', [0, 1])
def test_authored_facts_win_over_stdout_and_numeric_code(code):
    from reveal.mcp_server import _run_and_capture, _ToolFailure

    def authored():
        print('preceding output')
        raise NavSourceFailure(code, execution_facts=failure_execution_facts(FailureCause.ANALYSIS),
                               public_diagnostic='required source read failed')

    result = _run_and_capture(authored)
    assert isinstance(result, _ToolFailure)
    assert result.count('required source read failed') == 1 and 'preceding output' not in result


def test_bare_exit_and_literal_strings_remain_unclassified(source, monkeypatch):
    import reveal.cli.routing.file as file_route  # the file route's handle_file, which reveal_nav's command line reaches
    from reveal.mcp_server import _run_and_capture, _ToolFailure

    literal = '[reveal error: literal]\n[reveal exited with code 1]'

    def ordinary(*args, **kwargs):
        print(literal)
        raise SystemExit(1)

    result = _run_and_capture(ordinary)
    assert not isinstance(result, _ToolFailure) and result.strip() == literal
    monkeypatch.setattr(file_route, 'handle_file', ordinary)
    answer = _sdk(_arguments(source, flag='', view='effects'))  # the canonical view: no retirement note to add
    assert not answer.is_error and _text(answer).strip() == literal


@pytest.mark.parametrize('flag', FLAGS)
def test_empty_populated_and_range_successes_keep_complete_text(source, flag):
    from reveal.mcp_server import reveal_nav

    for element in ('empty', 'work', ':4-6'):
        direct = reveal_nav(**_arguments(source, element, flag))
        answer = _sdk(_arguments(source, element, flag))
        assert not answer.is_error and _text(answer).rstrip() == direct.rstrip()
        assert 'cannot read' not in direct and 'could not find function' not in direct


def test_ambiguity_and_file_loss_warnings_remain_successful(source, fault):
    ambiguous = _sdk(_arguments(source, 'ambiguous', transitive=True))
    assert not ambiguous.is_error and 'ambiguous' in _text(ambiguous)
    assert 'analysis is incomplete' in _text(ambiguous)
    unreadable = source.parent / 'unreadable.py'
    unreadable.write_text('def unrelated():\n    return 1\n', encoding='utf-8')
    fault['unreadable'] = unreadable.resolve()
    partial = _sdk(_arguments(source, 'work', transitive=True))
    assert not partial.is_error and 'logging.info' in _text(partial)
    assert 'could not be analyzed' in _text(partial)


def test_disappearance_after_cli_preflight_exits_2(source, monkeypatch):
    # The facts say INVALID_REQUEST (the requested file is gone); D6 exits 2 (BACK-2527, was 1).
    import reveal.registry as registry

    real_get = registry.get_analyzer
    constructions = []

    def get(path, **kwargs):
        original = real_get(path, **kwargs)

        def construct(request):
            constructions.append(request)
            Path(request).unlink()
            return original(request)
        return construct

    monkeypatch.setattr(registry, 'get_analyzer', get)
    run = _run_reveal_direct(source, 'empty', '--effects', '--format', 'json')
    assert constructions == [str(source)]
    assert run.returncode == 2 and run.stdout == '' and run.stderr.count('cannot read') == 1


def test_cli_missing_and_absent_exit_2_with_stderr(source):
    for path, element in [(source.parent / 'missing.py', 'empty'), (source, 'absent')]:
        result = _run_reveal_direct(path, element, '--effects', '--format', 'json')
        assert result.returncode == 2
        assert result.stderr
    # A missing path is the file route's refusal: in JSON it answers the invalid-request document (BACK-2325, S4); an
    # absent element is the element view's own failure, stdout empty as before.
    missing = _run_reveal_direct(source.parent / 'missing.py', 'empty', '--effects', '--format', 'json')
    document = json.loads(missing.stdout)
    assert document['type'] == 'element_view' and document['meta']['errors'][0]['code'] == 'invalid_request'
    assert _run_reveal_direct(source, 'absent', '--effects', '--format', 'json').stdout == ''


def test_unexpected_constructor_failure_is_masked_and_logged(source, monkeypatch, caplog):
    import reveal.registry as registry

    def construct(path):
        raise RuntimeError('PRIVATE_NAV_ANALYSIS_MARKER')

    monkeypatch.setattr(registry, 'get_analyzer', lambda *args, **kwargs: construct)
    with caplog.at_level(logging.ERROR):
        answer = _sdk(_arguments(source))
    assert answer.is_error and 'PRIVATE_NAV_ANALYSIS_MARKER' not in _text(answer)
    assert 'PRIVATE_NAV_ANALYSIS_MARKER' in caplog.text


_SERVER = '''
from pathlib import Path
from reveal import mcp_server
from reveal import registry
original = registry.get_analyzer

def analyzer(path, **kwargs):
    if Path(path).name == 'crash.py':
        def crash(request):
            raise RuntimeError('PRIVATE_STDIO_NAV_MARKER')
        return crash
    if Path(path).name == 'denied.py':
        def denied(request):
            raise PermissionError(13, 'PUBLIC_SOURCE_DENIED', request)
        return denied
    return original(path, **kwargs)

registry.get_analyzer = analyzer
mcp_server.main()
'''


def test_stdio_source_failures_recovery_ranges_and_private_masking(tmp_path, source):
    # The server's stubbed analyzer fails these two by name; they exist, so the CLI's route reaches it (BACK-2627 X13).
    for name in ('denied.py', 'crash.py'):
        (source.parent / name).write_text('def empty():\n    return 1\n', encoding='utf-8')

    async def scenario(session):
        for flag in FLAGS:
            missing = await session.call_tool('reveal_nav', _arguments(source.parent / 'missing.py', flag=flag))
            assert missing.is_error, _text(missing)
            _diagnostic(_text(missing), True)
            empty = await session.call_tool('reveal_nav', _arguments(source, flag=flag))
            assert not empty.is_error and 'cannot read' not in _text(empty)
            # flag is the CLI's flag: --effects, --sideeffects and --boundary say their rows' notes, --inputs none
            assert _text(empty).count('deprecated') == (flag != 'inputs')
            absent = await session.call_tool('reveal_nav', _arguments(source, 'absent', flag))
            assert absent.is_error
            _diagnostic(_text(absent), False)
            ranged = await session.call_tool('reveal_nav', _arguments(source, ':4-6', flag))
            assert not ranged.is_error and 'could not find function' not in _text(ranged)
            denied = await session.call_tool('reveal_nav', _arguments(source.parent / 'denied.py', flag=flag))
            assert denied.is_error and _text(denied).count('PUBLIC_SOURCE_DENIED') == 1
        value = await session.call_tool('reveal_nav', _arguments(source, 'work', 'varflow', flag_value='value'))
        assert not value.is_error and 'deprecated' not in _text(value)
        warning = await session.call_tool('reveal_nav', _arguments(source, 'ambiguous', transitive=True))
        assert not warning.is_error and 'ambiguous' in _text(warning)
        crashed = await session.call_tool('reveal_nav', _arguments(source.parent / 'crash.py'))
        assert crashed.is_error and 'PRIVATE_STDIO_NAV_MARKER' not in _text(crashed)
        recovered = await session.call_tool('reveal_nav', _arguments(source, 'work'))
        assert not recovered.is_error and 'logging.info' in _text(recovered)
    _stdio(tmp_path, scenario, code=_SERVER)
    assert 'PRIVATE_STDIO_NAV_MARKER' in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')


@pytest.mark.parametrize('exit_zero,expected', [(False, 3), (True, 0)])
def test_check_read_override_stays_outside_nav_adoption(source, monkeypatch, exit_zero, expected):
    import errno
    import reveal.registry as registry

    def construct(path):
        raise PermissionError(errno.EACCES, 'controlled check read', path)

    monkeypatch.setattr(registry, 'get_analyzer', lambda *args, **kwargs: construct)
    extra = ('--exit-zero',) if exit_zero else ()
    run = _run_reveal_direct('check', source, *extra, '--format', 'json')
    assert run.returncode == expected and run.stdout == ''
    assert run.stderr.count('controlled check read') == 1
